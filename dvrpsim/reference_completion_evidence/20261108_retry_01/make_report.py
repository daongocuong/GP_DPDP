"""Render a UTF-8 report from terminal supervision and loader artifacts."""
from pathlib import Path
import json
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
status = json.loads((HERE/'supervisor_status.json').read_text())
assert status['status'] != 'RUNNING', 'Wait for both retries and verification to finish'
preflight = json.loads((HERE/'preflight.json').read_text())
diagnosis = json.loads((HERE/'old_interruption_diagnosis.json').read_text())
lines = [
    '# Hoàn thiện reference VNSME cho gp-fitness-vnsme-v2', '',
    f"Trạng thái tác vụ: **{status['status']}**.", '',
    f"Bắt đầu: {status['started_at']}. Kết thúc: {status['ended_at']}.", '',
    '## Lượt bị gián đoạn trước đây', '',
    'Giữ trạng thái **INTERRUPTED**, nguyên nhân chưa được xác minh. Hai lượt',
    'cũ không có result.json cuối, failure.json hoặc mã thoát của tiến trình.',
    'Thư mục kỳ cuối chỉ có đầu vào và solution_before.json, không có invocation.json hoàn tất.', '',
    '| Instance | Kỳ cuối bắt đầu (thư mục) | Số invocation đã hoàn tất |',
    '| --- | --- | ---: |',
]
for row in diagnosis['runs']:
    lines.append(f"| {row['instance']} | {row['last_epoch']} | {row['completed_invocations']} |")
lines += [
    '', 'Các dòng TimeOut!! trong những kỳ trước đó đi kèm exit code 0 và SUCCESS:',
    'đây là giới hạn tìm kiếm nội bộ, không chứng minh nguyên nhân mất tiến trình.',
    'Truy vấn sự kiện Windows có ghi nhận trạng thái nguồn thấp; chưa có bằng chứng',
    'liên kết trực tiếp chúng với việc dừng Python/Java. Truy vấn crash và resource',
    'exhaustion trong cửa sổ đã lưu không tìm thấy sự kiện Python/Java phù hợp.',
    'Chi tiết nằm trong old_interruption_diagnosis.json, old_power_events.json',
    'và old_crash_event_query.json; không sửa interrupted.json lịch sử.', '',
    '## Giới hạn thời gian và provenance', '',
    '- Java gốc kiểm tra thời gian tìm kiếm khoảng 540 giây từ đầu invocation.',
    '  Đây là kiểm tra tại các điểm trong thuật toán, không phải hard timeout cho mọi operator.',
    '- Adapter giới hạn subprocess mỗi kỳ bằng min(600, ngân sách tổng còn lại).',
    '- Runner giới hạn cả lượt bằng 3.600 giây; supervisor có hard deadline ngoài',
    '  3.630 giây để dành thời gian khởi tạo và ghi artifact.',
    '- Mọi invocation đã hoàn tất của reference 2–4 dùng effective timeout 600 giây.',
    '  Tăng giới hạn tổng từ 1.800 lên 3.600 không thay ngân sách tìm kiếm mỗi kỳ',
    '  hoặc công thức J; loader lưu budget riêng của mỗi reference.',
    '- Java build, class, thư viện, simulator, scorer và các dependency runtime',
    '  được đối chiếu hash trước khi chạy. Không build lại và không sửa mã production.',
    '- Runner so với manifest 2–4 chỉ khác guard từ chối các tên policy đã gỡ.',
    '  Bỏ đúng guard đó cho hash khớp bản cũ; nhánh VNSME không đổi.',
    '- Seed môi trường 0; Java gốc không nhận seed qua CLI, giữ nguyên cách gọi.',
    f"- SHA-256 build manifest: `{preflight['java_build_sha256']}`.",
    '- Dữ liệu, vị trí ban đầu, dispatch 600 giây, docking 1.800 giây, load/unload',
    '  240 giây mỗi đơn vị, lambda 10.000 và horizon 7 ngày giữ nguyên.', '',
    '## Kết quả hai lượt mới', '',
    '| Instance | Trạng thái | Exit code | Kỳ cuối (thư mục) | Thời gian runner (giây) | Thời gian giám sát (giây) | Đơn/item hoàn tất |',
    '| --- | --- | ---: | --- | ---: | ---: | --- |',
]
for row in status['runs']:
    result = row.get('runner_result', {})
    lines.append(f"| {row['instance']} | {row['status']} | {row['returncode']} | {row.get('last_epoch')} | "
        f"{result.get('total_wall_seconds', '—')} | {row['elapsed_seconds']:.3f} | "
        f"{result.get('completed_original_orders', '—')}/{result.get('completed_items', '—')} |")
    lines += ['', f"Instance {row['instance']}: `{row['run_directory']}`."]
lines += [
    '', 'Hai lượt chạy tuần tự: 5 kết thúc trước khi bắt đầu 6. Mỗi lượt dùng CWD',
    'và solution.json riêng. Giám sát lưu heartbeat JSONL, cây tiến trình, PID,',
    'bộ nhớ và thread dump cho các kỳ kéo dài. Java stdout/stderr vẫn theo adapter',
    'gốc, được ghi vào archive sau khi invocation trả về. Mã thoát Windows quan sát',
    'thêm nằm trong observed_process_exits.jsonl.', '',
    'Lượt 5 mới dùng khoảng 3.268 giây, lớn hơn giới hạn tổng 1.800 giây cũ.',
    'Điều này xác nhận budget cũ không đủ cho trajectory mới, không chứng minh',
    'nguyên nhân dừng của trajectory cũ khi chưa có mã thoát.', '',
    'Helper tạm thời yêu cầu hệ thống giữ thức trong lúc supervisor chạy và nhả',
    'yêu cầu khi supervisor kết thúc, dùng [SetThreadExecutionState của Windows](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).', '',
]
evaluation = status.get('evaluation')
if evaluation:
    lines += [
        '## Summary và loader', '',
        f"Summary: `{evaluation['summary']}`.",
        f"SHA-256: `{evaluation['summary_sha256']}`.", '',
        'Loader **PASS**: đủ train 2–5 và validation 6, mọi J dương, policy/version,',
        'seed, build, input/config, artifact hash, guard, hoàn tất và chấm lại log hợp lệ.', '',
        '| Instance | VNSME J | GP J đã lưu | J_GP/J_VNSME |',
        '| --- | ---: | ---: | ---: |',
    ]
    for instance, score in evaluation['vnsme_scores'].items():
        numerator = evaluation['gp_scores'][instance]
        ratio = float(numerator)/float(score)
        lines.append(f'| {instance} | {score} | {numerator} | {ratio:.12f} |')
    lines += [
        '', '## Cây GP cố định', '',
        f"Cây: `{evaluation['tree_file']}`.",
        f"SHA-256 file: `{evaluation['tree_file_sha256']}`.",
        f"SHA-256 cây canonical: `{evaluation['tree_sha256']}`.",
        'Hash file bao gồm metadata; hash cây dùng biểu diễn canonical của các node.',
        'Các tử số J lấy từ log GP đã lưu; hash log và scorer độc lập được xác minh lại.',
        'Không chạy thêm rollout GP, không tiến hóa và không chọn lại cây.', '',
        f"Fitness train v2: **{evaluation['train']['fitness']:.12f}**.",
        f"Tỷ số validation instance 6: **{evaluation['validation_ratio']:.12f}**.", '',
        'Công thức train là mean(J_GP(i)/J_VNSME(i)), i thuộc 2–5.',
        'Validation là J_GP(6)/J_VNSME(6). Fitness lịch sử giữ nguyên định nghĩa cũ.', '',
        'Lệnh huấn luyện để chạy sau, dùng thư mục output mới:', '', '```powershell',
        r'Set-Location C:\Users\Cuongdz\Documents\LA\dvrpsim',
        r'.\.venv\Scripts\python.exe train_dpdp_gp_multinstance.py --baseline-summary migration_runs\vnsme_reference_ready\summary.json --output gp_runs\vnsme_v2_new_training',
        '```', '',
    ]
else:
    lines += ['', 'Không có summary được chấp nhận hoặc fitness v2 đầy đủ.',
              'Xem supervisor_status.json và các instance_*_supervision.json để chẩn đoán.',
              f"Lỗi: `{status.get('error', status['status'])}`.", '']
preserved = status.get('historical_preservation', {})
lines += ['## Phạm vi và bảo toàn', '',
    f"Đã kiểm tra {preserved.get('files_checked')} artifact lịch sử; unchanged = {preserved.get('unchanged')}.",
    'Không chạy/chấm điểm instance 7–8 hoặc 15–16. Không huấn luyện GP.',
    'Chỉ thêm artifact chạy mới và helper chẩn đoán trong thư mục bằng chứng này.',
    'Bằng chứng chính: preflight.json, supervisor_status.json, adopt_invocation.json,',
    'fitness_v2_verification.json và historical_preservation.json.', '']
text = unicodedata.normalize('NFC', '\n'.join(lines))
assert '\ufffd' not in text
report = HERE/'REFERENCE_COMPLETION_REPORT.md'
report.write_text(text, encoding='utf-8')
assert report.read_bytes().decode('utf-8') == text.replace('\n', '\r\n') or report.read_text(encoding='utf-8') == text
print(report)
