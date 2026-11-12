"""Small bounded symbolic GP. Only five baseline features reach the tree.

No eval(), simulator access, files or instance IDs in expression evaluation.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from dpdp_insertion import FEATURE_UNITS

FEATURES = tuple(FEATURE_UNITS)
PRIMITIVES = ('+', '-', '*', '/')
FORMAT = 'dpdp-gp-tree-v1'
NUMERIC_POLICY = dict(epsilon=1e-9, protected_division='return numerator if abs(denominator)<=epsilon',
                      saturation=1e12, nonfinite='raise NumericTreeError; invalidate entire rollout')


class TreeError(ValueError):
    pass


class NumericTreeError(TreeError):
    pass


@dataclass(frozen=True)
class Limits:
    max_depth: int = 4  # root is depth 0
    max_nodes: int = 31


@dataclass(frozen=True)
class Node:
    op: str
    value: object = None
    args: tuple = ()

    # Ghi chú: Chuyển cây biểu thức thành cấu trúc dict có thể lưu JSON.
    def data(self):
        if self.op in ('feature', 'const'):
            return {self.op: self.value}
        return {'op': self.op, 'args': [a.data() for a in self.args]}

    # Ghi chú: Biểu diễn cây thành công thức dễ đọc để xem cây GP đã học gì.
    def text(self):
        if self.op in ('feature', 'const'):
            return str(self.value)
        return f'({self.args[0].text()} {self.op} {self.args[1].text()})'


# Ghi chú: Kiểm terminal/phép toán, hằng hữu hạn và giới hạn kích thước: tối đa depth 4, 31 node.
def validate_tree(tree, limits=Limits()):
    if not (0 <= limits.max_depth <= 4 and 1 <= limits.max_nodes <= 31):
        raise TreeError('limits exceed pilot hard caps')
    stack, count, deepest = [(tree, 0)], 0, 0
    while stack:
        node, depth = stack.pop()
        count += 1
        deepest = max(deepest, depth)
        if count > limits.max_nodes or depth > limits.max_depth:
            raise TreeError('tree depth/node limit exceeded')
        if not isinstance(node, Node):
            raise TreeError('expected Node')
        if node.op == 'feature':
            if node.value not in FEATURES or node.args:
                raise TreeError('unknown feature or invalid terminal arity')
        elif node.op == 'const':
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)) or abs(node.value) > 1e12 or not math.isfinite(node.value) or node.args:
                raise TreeError('invalid finite constant')
        elif node.op in PRIMITIVES:
            if len(node.args) != 2 or node.value is not None:
                raise TreeError('binary primitive required')
            stack.extend((child, depth+1) for child in node.args)
        else:
            raise TreeError('unknown primitive')
    return count, deepest


# Ghi chú: Dựng Node đệ quy từ JSON, từ chối schema sai hoặc cây quá sâu.
def parse_node(data, depth=0):
    if depth > 4 or not isinstance(data, dict):
        raise TreeError('invalid node/depth')
    if set(data) == {'feature'}:
        return Node('feature', data['feature'])
    if set(data) == {'const'}:
        return Node('const', data['const'])
    if set(data) == {'op', 'args'} and isinstance(data['args'], list) and len(data['args']) == 2:
        return Node(data['op'], args=tuple(parse_node(a, depth+1) for a in data['args']))
    raise TreeError('invalid tree schema')


# Ghi chú: Chuẩn hóa cây thành JSON có thứ tự ổn định để so sánh, phá hòa và tạo hash.
def canonical(tree):
    validate_tree(tree)
    return json.dumps(tree.data(), sort_keys=True, separators=(',', ':'), allow_nan=False)


# Ghi chú: Tính định danh SHA-256 từ biểu diễn chuẩn hóa của cây.
def tree_hash(tree):
    return hashlib.sha256(canonical(tree).encode()).hexdigest()


# Ghi chú: Lưu cây cùng ngữ nghĩa feature/phép toán, giới hạn và metadata huấn luyện vào file mới.
def save_tree(path, tree, training=None, limits=Limits()):
    size, depth = validate_tree(tree, limits)
    value = dict(format=FORMAT, tree=tree.data(), expression=tree.text(), tree_sha256=tree_hash(tree),
                 primitives=list(PRIMITIVES), features=[{'name': f, 'unit': FEATURE_UNITS[f]} for f in FEATURES],
                 numeric_policy=NUMERIC_POLICY, limits=vars(limits), nodes=size, depth=depth,
                 training=training or {})
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
    return value


# Ghi chú: Nạp cây và đối chiếu schema, ngữ nghĩa số học, hash và kích thước trước khi sử dụng.
def load_tree(path):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('format') != FORMAT or payload.get('primitives') != list(PRIMITIVES):
        raise TreeError('unsupported format/primitive set')
    if payload.get('features') != [{'name': f, 'unit': FEATURE_UNITS[f]} for f in FEATURES] or payload.get('numeric_policy') != NUMERIC_POLICY:
        raise TreeError('feature or numeric semantics mismatch')
    try:
        limits = Limits(**payload['limits'])
        tree = parse_node(payload['tree'])
        size, depth = validate_tree(tree, limits)
    except (KeyError, TypeError, RecursionError) as exc:
        raise TreeError(f'invalid model: {exc}') from exc
    if payload.get('tree_sha256') != tree_hash(tree) or payload.get('nodes') != size or payload.get('depth') != depth:
        raise TreeError('model hash/shape mismatch')
    return tree, payload


class TreeRanker:
    # Ghi chú: Kiểm cây và khởi tạo bộ đếm cho các lần chấm điểm candidate.
    def __init__(self, tree):
        validate_tree(tree)
        self.tree = tree
        self.stats = dict(evaluations=0, protected_divisions=0, saturations=0, numeric_errors=0)

    # Ghi chú: Tính điểm xếp hạng từ đúng năm feature; điểm nhỏ hơn được ưu tiên, đây chưa phải điểm J của rollout.
    def __call__(self, features, vehicle_num=None):
        # vehicle_num is the baseline call signature, NOT a GP terminal.
        # Only the whitelisted scalars below are visible to evaluation.
        self.stats['evaluations'] += 1
        # Ghi chú: Từ chối NaN/vô cực và chặn độ lớn tại 1e12 để kiểm soát phép tính của cây.
        def safe(value):
            if not math.isfinite(value):
                raise NumericTreeError('nonfinite arithmetic/feature')
            if abs(value) > 1e12:
                self.stats['saturations'] += 1
                return math.copysign(1e12, value)
            return value
        # Ghi chú: Tính cây đệ quy; phép chia có mẫu gần 0 trả về tử số theo numeric policy.
        def evaluate(node, values):
            if node.op == 'feature':
                return values[node.value]
            if node.op == 'const':
                return safe(float(node.value))
            a, b = (evaluate(child, values) for child in node.args)
            if node.op == '+':
                return safe(a+b)
            if node.op == '-':
                return safe(a-b)
            if node.op == '*':
                return safe(a*b)
            if abs(b) <= NUMERIC_POLICY['epsilon']:
                self.stats['protected_divisions'] += 1
                return a
            return safe(a/b)
        try:
            if set(features) != set(FEATURES):
                raise NumericTreeError('feature schema mismatch')
            values = {f: safe(float(features[f])) for f in FEATURES}
            return evaluate(self.tree, values)
        except (ArithmeticError, ValueError, TypeError) as exc:
            self.stats['numeric_errors'] += 1
            raise NumericTreeError(str(exc)) from exc


# Ghi chú: Sinh cây ngẫu nhiên từ feature, hằng số và bốn phép toán theo RNG được truyền vào.
def random_tree(rng, depth=3, full=False):
    if depth == 0 or (not full and rng.random() < .35):
        if rng.random() < .8:
            return Node('feature', rng.choice(FEATURES))
        return Node('const', round(rng.uniform(-2, 2), 3))
    return Node(rng.choice(PRIMITIVES), args=(random_tree(rng, depth-1, full), random_tree(rng, depth-1, full)))


# Ghi chú: Liệt kê đường đi đến mọi node để chọn vị trí lai ghép hoặc đột biến.
def paths(tree, path=()):
    yield path
    for i, child in enumerate(tree.args):
        yield from paths(child, path+(i,))


# Ghi chú: Lấy cây con tại một đường đi, mỗi chỉ số xác định nhánh con tiếp theo.
def subtree(tree, path):
    for i in path:
        tree = tree.args[i]
    return tree


# Ghi chú: Tạo cây mới với một nhánh được thay thế; giữ nguyên cây cha bất biến.
def replace_subtree(tree, path, replacement):
    if not path:
        return replacement
    children = list(tree.args)
    children[path[0]] = replace_subtree(children[path[0]], path[1:], replacement)
    return Node(tree.op, tree.value, tuple(children))


# Ghi chú: Ghép nhánh từ cây b vào cây a; thử tối đa 10 lần và giữ a nếu không tạo được cây hợp giới hạn.
def crossover(rng, a, b, limits=Limits()):
    for _ in range(10):
        child = replace_subtree(a, rng.choice(list(paths(a))), subtree(b, rng.choice(list(paths(b)))))
        try:
            validate_tree(child, limits)
            return child
        except TreeError:
            pass
    return a


# Ghi chú: Thay một nhánh bằng cây ngẫu nhiên; giữ cây cha nếu các lần thử đều vượt giới hạn.
def mutate(rng, parent, limits=Limits()):
    for _ in range(10):
        path = rng.choice(list(paths(parent)))
        child = replace_subtree(parent, path, random_tree(rng, min(2, limits.max_depth-len(path))))
        try:
            validate_tree(child, limits)
            return child
        except TreeError:
            pass
    return parent


# Ghi chú: Tạo quần thể đầu gồm hai công thức đơn giản và các cây ngẫu nhiên theo seed.
def initial_population(rng, size=6):
    if size < 2:
        raise TreeError('population size must be >=2')
    # Fixed simple seeds plus seeded random grow/full; no baseline coefficient tuning.
    population = [Node('feature', FEATURES[0]), Node('+', args=(Node('feature', FEATURES[0]), Node('feature', FEATURES[1])))]
    while len(population) < size:
        population.append(random_tree(rng, depth=rng.randint(1, 3), full=len(population)%2 == 0))
    return population


# Ghi chú: Tạo thế hệ mới bằng elitism, tournament selection, crossover và mutation; mục tiêu là giảm fitness.
def breed(rng, evaluated, size, tournament=3, crossover_rate=.8, mutation_rate=.3, elitism=1, limits=Limits()):
    # Ghi chú: Xếp cây theo fitness rồi số node và biểu diễn chuẩn để phá hòa ổn định.
    def key(entry):
        return entry[0], validate_tree(entry[1])[0], canonical(entry[1])
    ranked = sorted(evaluated, key=key)
    # Ghi chú: Lấy mẫu tournament và chọn cây có khóa xếp hạng nhỏ nhất.
    def select():
        return min((rng.choice(ranked) for _ in range(tournament)), key=key)[1]
    # Ghi chú: Elitism giữ trực tiếp các cây tốt nhất; những vị trí còn lại được sinh bằng chọn lọc/lai/đột biến.
    next_generation = [tree for _, tree in ranked[:elitism]]
    while len(next_generation) < size:
        child = select()
        if rng.random() < crossover_rate:
            child = crossover(rng, child, select(), limits)
        if rng.random() < mutation_rate:
            child = mutate(rng, child, limits)
        validate_tree(child, limits)
        next_generation.append(child)
    return next_generation
