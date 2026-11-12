# Repository inventory — GP–DPDP

Snapshot metadata ngày 2026-11-10, Asia/Bangkok, trước khi tạo bảy báo cáo cleanup. Git root: C:/Users/Cuongdz/Documents/LA; branch complete-gp-dpdp; HEAD 0bd773291d5d9034f1e7b81688bc2dfaf87308c7. Working tree có 9 tracked files modified và nhiều untracked v3 source/protocol/evidence; không commit/reset/clean.

## Phương pháp và giới hạn

Quét toàn LA bằng directory enumeration và file stat, gồm hidden files, .git, cả hai virtual environments, ignored runs, datasets và docs. Không có lỗi truy cập hoặc symlink trong snapshot. Không thực thi project code, import project, training, Java search, simulation hoặc test discovery. Không đọc secrets/credentials; sealed instance_7/8/15/16 chỉ được stat metadata, không mở contents. Không hash toàn dataset hoặc mọi large artifact. Phân tích nội dung có giới hạn 744 source/config/doc/metadata files (~10.76 MB), selected Java source/library duplicate trees và ba cặp stderr lớn. Source/reference search không exhaustively đọc mọi cache/log/JSON; không thấy reference không có nghĩa an toàn xóa.

Dung lượng là tổng logical file lengths, không phải allocated NTFS disk blocks; không tính directory records/ADS/compression overhead, không khẳng định bytes vật lý có thể thu hồi. Các bảng parent/child lồng nhau KHÔNG được cộng. File/dir counts ở snapshot trước báo cáo; bảy báo cáo mới sẽ tăng nhẹ total. Directory count gồm LA root.

## Tổng quan

- Files: **55,782**.
- Directories: **5,828** gồm root; 5,827 dưới root.
- Tổng logical bytes: **2,034,035,362 B = 2.034 GB = 1.894 GiB**.
- Tracked tính theo git ls-files hiện có; ignored theo git check-ignore --stdin; .git internal tách riêng.

| Git group | Files | Bytes | Size |
| --- | --- | --- | --- |
| tracked | 7,937 | 87,080,081 | 83.046 MiB |
| untracked | 651 | 20,195,719 | 19.260 MiB |
| ignored | 46,663 | 1,899,928,915 | 1811.913 MiB |
| gitInternal | 531 | 26,830,647 | 25.588 MiB |


## Thư mục cấp cao và root files

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim` | 50,459 | 1,977,799,129 | 1886.176 MiB |
| `.git` | 531 | 26,830,647 | 25.588 MiB |
| `VNSME` | 3,786 | 13,545,151 | 12.918 MiB |
| `.venv` | 994 | 13,145,539 | 12.537 MiB |
| `docs` | 6 | 95,755 | 0.091 MiB |

| Root file | Bytes | Git |
| --- | --- | --- |
| `.gitignore` | 501 | tracked |
| `1-s2.0-S2192437625000081-main.pdf` | 1,880,233 | tracked |
| `2202.01256v1.pdf` | 662,141 | tracked |
| `GHI_CHU_DVRPSIM.md` | 32,336 | tracked |
| `Ke_hoach_GP_DPDP.md` | 39,456 | tracked |
| `TIEN_DO_GP_DPDP.md` | 4,474 | untracked |


## Thư mục trực tiếp dưới dvrpsim

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/vnsme_runs` | 26,031 | 1,042,662,395 | 994.360 MiB |
| `dvrpsim/gp_runs` | 1,994 | 435,512,744 | 415.337 MiB |
| `dvrpsim/migration_runs` | 11,385 | 261,552,889 | 249.436 MiB |
| `dvrpsim/.venv` | 6,031 | 142,538,180 | 135.935 MiB |
| `dvrpsim/examples` | 34 | 34,867,505 | 33.252 MiB |
| `dvrpsim/third_party` | 3,947 | 27,449,855 | 26.178 MiB |
| `dvrpsim/vnsme_evidence` | 680 | 21,195,611 | 20.214 MiB |
| `dvrpsim/reference_completion_evidence` | 40 | 3,491,975 | 3.330 MiB |
| `dvrpsim/datasets` | 34 | 2,849,657 | 2.718 MiB |
| `dvrpsim/dataset_runs` | 32 | 1,492,633 | 1.423 MiB |
| `dvrpsim/baseline_runs` | 41 | 1,016,413 | 0.969 MiB |
| `dvrpsim/migration_evidence` | 7 | 929,999 | 0.887 MiB |
| `dvrpsim/__pycache__` | 31 | 482,983 | 0.461 MiB |
| `dvrpsim/run_logs` | 5 | 345,312 | 0.329 MiB |
| `dvrpsim/src` | 38 | 344,741 | 0.329 MiB |
| `dvrpsim/gp_evidence` | 13 | 205,950 | 0.196 MiB |
| `dvrpsim/docs` | 29 | 186,153 | 0.178 MiB |
| `dvrpsim/feasibility_schedule_evidence` | 7 | 77,260 | 0.074 MiB |
| `dvrpsim/dataset_evidence` | 3 | 64,682 | 0.062 MiB |
| `dvrpsim/scoring_reference` | 8 | 37,337 | 0.036 MiB |
| `dvrpsim/baseline_evidence` | 5 | 33,136 | 0.032 MiB |
| `dvrpsim/protocols` | 10 | 11,788 | 0.011 MiB |
| `dvrpsim/.github` | 1 | 384 | 0.000 MiB |

Các source/test/config nằm trực tiếp dưới dvrpsim không nằm trong bảng directory con; chúng đã được tính vào total.

## Số file theo extension

| Extension | Files | Bytes | Size |
| --- | --- | --- | --- |
| `.json` | 30,335 | 467,222,381 | 445.578 MiB |
| `.txt` | 9,173 | 1,108,207,484 | 1056.869 MiB |
| `.class` | 7,526 | 25,384,946 | 24.209 MiB |
| `.py` | 3,038 | 44,507,606 | 42.446 MiB |
| `.pyc` | 2,863 | 60,717,013 | 57.904 MiB |
| `[none]` | 1,259 | 6,350,545 | 6.056 MiB |
| `.log` | 387 | 30,939,288 | 29.506 MiB |
| `.pyi` | 316 | 2,157,300 | 2.057 MiB |
| `.csv` | 290 | 94,394,161 | 90.021 MiB |
| `.md` | 85 | 601,678 | 0.574 MiB |
| `.lib` | 66 | 485,530 | 0.463 MiB |
| `.pyd` | 64 | 21,254,656 | 20.270 MiB |
| `.f90` | 62 | 30,836 | 0.029 MiB |
| `.jsonl` | 49 | 119,142,858 | 113.623 MiB |
| `.typed` | 32 | 769 | 0.001 MiB |
| `.h` | 27 | 417,018 | 0.398 MiB |
| `.f` | 25 | 12,340 | 0.012 MiB |
| `.exe` | 24 | 3,382,198 | 3.226 MiB |
| `.java` | 21 | 532,862 | 0.508 MiB |
| `.sample` | 14 | 26,788 | 0.026 MiB |
| `.before` | 11 | 122,033 | 0.116 MiB |
| `.tpl` | 8 | 8,896 | 0.008 MiB |
| `.pyf` | 8 | 2,851 | 0.003 MiB |
| `.pxd` | 7 | 66,159 | 0.063 MiB |
| `.xml` | 6 | 1,081,755 | 1.032 MiB |
| `.sha256` | 5 | 438 | 0.000 MiB |
| `.rst` | 5 | 30,976 | 0.030 MiB |
| `.c` | 5 | 87,869 | 0.084 MiB |
| `.npy` | 5 | 1,033 | 0.001 MiB |
| `.bat` | 4 | 2,820 | 0.003 MiB |
| `.apache` | 4 | 40,696 | 0.039 MiB |
| `.bsd` | 4 | 5,376 | 0.005 MiB |
| `.tab` | 4 | 49,667 | 0.047 MiB |
| `.pyx` | 4 | 23,291 | 0.022 MiB |
| `.cfg` | 3 | 710 | 0.001 MiB |
| `.yml` | 3 | 2,934 | 0.003 MiB |
| `.patch` | 3 | 12,422 | 0.012 MiB |
| `.dll` | 3 | 21,739,168 | 20.732 MiB |
| `.gz` | 3 | 701 | 0.001 MiB |
| `.build` | 3 | 7,068 | 0.007 MiB |
| `.pdf` | 2 | 2,542,374 | 2.425 MiB |
| `.toml` | 2 | 23,066 | 0.022 MiB |
| `.fish` | 2 | 4,552 | 0.004 MiB |
| `.ps1` | 2 | 58,378 | 0.056 MiB |
| `.pem` | 2 | 509,810 | 0.486 MiB |
| `.npz` | 2 | 819 | 0.001 MiB |
| `.docx` | 1 | 13,388 | 0.013 MiB |
| `.iml` | 1 | 458 | 0.000 MiB |
| `.idx` | 1 | 124,020 | 0.118 MiB |
| `.pack` | 1 | 21,559,222 | 20.560 MiB |
| `.rev` | 1 | 17,616 | 0.017 MiB |
| `.pth` | 1 | 43 | 0.000 MiB |
| `.zi` | 1 | 105,015 | 0.100 MiB |
| `.template` | 1 | 1,855 | 0.002 MiB |
| `.js` | 1 | 3,677 | 0.004 MiB |
| `.ini` | 1 | 222 | 0.000 MiB |
| `.pc` | 1 | 198 | 0.000 MiB |
| `.pkl` | 1 | 716 | 0.001 MiB |
| `.cpp` | 1 | 6,012 | 0.006 MiB |
| `.fits` | 1 | 8,640 | 0.008 MiB |
| `.inc` | 1 | 17 | 0.000 MiB |
| `.f95` | 1 | 144 | 0.000 MiB |

Extension [none] gồm file không extension và dotfiles theo path.extname; không phải đều temporary. .pem chỉ được stat, không đọc/hash nội dung.

## 30 files lớn nhất

| # | Path | Bytes | Size | Git |
| --- | --- | --- | --- | --- |
| 1 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00062/java_stderr_live.txt` | 49,859,285 | 47.550 MiB | ignored |
| 2 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00062/stderr.txt` | 49,859,285 | 47.550 MiB | ignored |
| 3 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs/00062/java_stderr_live.txt` | 47,597,465 | 45.392 MiB | ignored |
| 4 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs/00062/stderr.txt` | 47,597,465 | 45.392 MiB | ignored |
| 5 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00061/java_stderr_live.txt` | 47,478,164 | 45.279 MiB | ignored |
| 6 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00061/stderr.txt` | 47,478,164 | 45.279 MiB | ignored |
| 7 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00088/java_stderr_live.txt` | 32,825,051 | 31.304 MiB | ignored |
| 8 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00088/stderr.txt` | 32,825,051 | 31.304 MiB | ignored |
| 9 | `dvrpsim/examples/case_studies/rmdp/data/180_2.txt` | 32,035,416 | 30.551 MiB | tracked |
| 10 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme/epochs/00061/stderr.txt` | 31,927,841 | 30.449 MiB | ignored |
| 11 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run/vnsme/epochs/00061/java_stderr_live.txt` | 29,152,845 | 27.802 MiB | ignored |
| 12 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run/vnsme/epochs/00061/stderr.txt` | 29,152,845 | 27.802 MiB | ignored |
| 13 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme/epochs/00062/stderr.txt` | 29,108,409 | 27.760 MiB | ignored |
| 14 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00100/java_stderr_live.txt` | 29,079,551 | 27.732 MiB | ignored |
| 15 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs/00100/stderr.txt` | 29,079,551 | 27.732 MiB | ignored |
| 16 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs/00061/java_stderr_live.txt` | 28,723,136 | 27.393 MiB | ignored |
| 17 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs/00061/stderr.txt` | 28,723,136 | 27.393 MiB | ignored |
| 18 | `dvrpsim/migration_runs/vnsme_reference/instance_5/vnsme/epochs/00061/stderr.txt` | 28,558,226 | 27.235 MiB | ignored |
| 19 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run/vnsme/epochs/00062/java_stderr_live.txt` | 28,386,899 | 27.072 MiB | ignored |
| 20 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run/vnsme/epochs/00062/stderr.txt` | 28,386,899 | 27.072 MiB | ignored |
| 21 | `dvrpsim/migration_runs/vnsme_reference/instance_5/vnsme/epochs/00062/stderr.txt` | 27,538,705 | 26.263 MiB | ignored |
| 22 | `dvrpsim/vnsme_runs/scale100_reference_20261109_r1/instance_13/vnsme/epochs/00021/stderr.txt` | 26,903,425 | 25.657 MiB | ignored |
| 23 | `dvrpsim/vnsme_runs/scale100_reference_20261109_r1/instance_13/vnsme/epochs/00020/stderr.txt` | 24,498,079 | 23.363 MiB | ignored |
| 24 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme/epochs/00088/stderr.txt` | 21,669,203 | 20.665 MiB | ignored |
| 25 | `.git/objects/pack/pack-7f1e72bc52834b1f07f8cce8a6237ae7353dd65f.pack` | 21,559,222 | 20.560 MiB | gitInternal |
| 26 | `dvrpsim/.venv/Lib/site-packages/numpy.libs/libscipy_openblas64_-ed4f167a5330424524f45258e7ca2c8d.dll` | 20,589,056 | 19.635 MiB | ignored |
| 27 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme/epochs/00100/stderr.txt` | 20,563,106 | 19.611 MiB | ignored |
| 28 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme/epochs/00104/stderr.txt` | 17,009,007 | 16.221 MiB | ignored |
| 29 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs/00100/java_stderr_live.txt` | 14,811,129 | 14.125 MiB | ignored |
| 30 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs/00100/stderr.txt` | 14,811,129 | 14.125 MiB | ignored |


## 30 directories lớn nhất

| # | Path | Files | Bytes | Size |
| --- | --- | --- | --- | --- |
| 1 | `dvrpsim` | 50,459 | 1,977,799,129 | 1886.176 MiB |
| 2 | `dvrpsim/vnsme_runs` | 26,031 | 1,042,662,395 | 994.360 MiB |
| 3 | `dvrpsim/gp_runs` | 1,994 | 435,512,744 | 415.337 MiB |
| 4 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1` | 2,161 | 352,033,515 | 335.725 MiB |
| 5 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run` | 2,156 | 344,190,370 | 328.246 MiB |
| 6 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme` | 2,150 | 340,131,762 | 324.375 MiB |
| 7 | `dvrpsim/vnsme_runs/v3_instance5_standalone_r1/run/vnsme/epochs` | 2,141 | 336,936,752 | 321.328 MiB |
| 8 | `dvrpsim/migration_runs` | 11,385 | 261,552,889 | 249.436 MiB |
| 9 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1` | 3,762 | 236,717,873 | 225.752 MiB |
| 10 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1` | 2,161 | 220,327,049 | 210.120 MiB |
| 11 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5` | 1,573 | 218,773,433 | 208.639 MiB |
| 12 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run` | 1,570 | 212,661,955 | 202.810 MiB |
| 13 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run` | 2,156 | 212,482,314 | 202.639 MiB |
| 14 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run/vnsme` | 1,567 | 210,784,910 | 201.020 MiB |
| 15 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme` | 2,150 | 208,407,043 | 198.752 MiB |
| 16 | `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1/instance_5/run/vnsme/epochs` | 1,560 | 207,572,084 | 197.956 MiB |
| 17 | `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1/run/vnsme/epochs` | 2,141 | 205,212,026 | 195.705 MiB |
| 18 | `dvrpsim/migration_runs/reference_retry_20261108_01` | 3,116 | 154,091,370 | 146.953 MiB |
| 19 | `dvrpsim/.venv` | 6,031 | 142,538,180 | 135.935 MiB |
| 20 | `dvrpsim/.venv/Lib` | 6,017 | 141,453,805 | 134.901 MiB |
| 21 | `dvrpsim/.venv/Lib/site-packages` | 6,017 | 141,453,805 | 134.901 MiB |
| 22 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5` | 1,543 | 135,371,678 | 129.100 MiB |
| 23 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme` | 1,538 | 133,738,731 | 127.543 MiB |
| 24 | `dvrpsim/migration_runs/reference_retry_20261108_01/instance_5/vnsme/epochs` | 1,529 | 130,543,709 | 124.496 MiB |
| 25 | `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1` | 392 | 124,853,910 | 119.070 MiB |
| 26 | `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1/fitness` | 385 | 121,385,414 | 115.762 MiB |
| 27 | `dvrpsim/gp_runs/vnsme_v2_new_training` | 392 | 121,081,554 | 115.472 MiB |
| 28 | `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1/fitness/rollouts` | 275 | 120,082,511 | 114.520 MiB |
| 29 | `dvrpsim/gp_runs/vnsme_v2_new_training/fitness` | 385 | 117,617,039 | 112.168 MiB |
| 30 | `dvrpsim/vnsme_runs/scale100_reference_20261109_r1` | 2,186 | 117,570,315 | 112.124 MiB |

Các dòng run/run-vnsme/epochs là nested views của cùng bytes. Không cộng các dòng này để ước lượng tiết kiệm.

## Inventory từng experiment family

### dvrpsim/gp_runs

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1` | 392 | 124,853,910 | 119.070 MiB |
| `dvrpsim/gp_runs/vnsme_v2_new_training` | 392 | 121,081,554 | 115.472 MiB |
| `dvrpsim/gp_runs/scale100_diagnostic_20261109_r1` | 82 | 100,468,232 | 95.814 MiB |
| `dvrpsim/gp_runs/multinstance_50_20261105` | 498 | 28,707,269 | 27.377 MiB |
| `dvrpsim/gp_runs/delta_j_diagnostic_20261109_r1` | 48 | 17,574,165 | 16.760 MiB |
| `dvrpsim/gp_runs/c10_instance3_diagnostic_20261109_r1` | 24 | 10,668,278 | 10.174 MiB |
| `dvrpsim/gp_runs/official_gp_multinstance_20261109` | 180 | 9,591,416 | 9.147 MiB |
| `dvrpsim/gp_runs/vnsme_v2_new_training_20261108_r1_audit` | 99 | 9,070,782 | 8.651 MiB |
| `dvrpsim/gp_runs/smoke_test_measure_20261109` | 173 | 8,859,116 | 8.449 MiB |
| `dvrpsim/gp_runs/comparison_20261105` | 25 | 2,176,855 | 2.076 MiB |
| `dvrpsim/gp_runs/pilot_20261105_v2` | 64 | 2,072,756 | 1.977 MiB |
| `dvrpsim/gp_runs/pilot_20261105` | 8 | 256,327 | 0.244 MiB |
| `dvrpsim/gp_runs/demo_adapter_smoke` | 9 | 132,084 | 0.126 MiB |

### dvrpsim/vnsme_runs

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/vnsme_runs/v3_instance5_standalone_r1` | 2,161 | 352,033,515 | 335.725 MiB |
| `dvrpsim/vnsme_runs/v3_references_3_6_20261109_recovery_r1` | 3,762 | 236,717,873 | 225.752 MiB |
| `dvrpsim/vnsme_runs/v3_instance5_recovery_20261110_r1` | 2,161 | 220,327,049 | 210.120 MiB |
| `dvrpsim/vnsme_runs/scale100_reference_20261109_r1` | 2,186 | 117,570,315 | 112.124 MiB |
| `dvrpsim/vnsme_runs/v3_instance6_validation_20261110_r1` | 2,203 | 30,713,822 | 29.291 MiB |
| `dvrpsim/vnsme_runs/v3_instance6_standalone_r1` | 2,203 | 24,795,373 | 23.647 MiB |
| `dvrpsim/vnsme_runs/v3_references_3_6_20261109_r1` | 3,748 | 18,171,192 | 17.329 MiB |
| `dvrpsim/vnsme_runs/v3_instance2_acceptance_20261109_r1` | 2,358 | 9,921,360 | 9.462 MiB |
| `dvrpsim/vnsme_runs/verified_instance2` | 1,698 | 7,421,556 | 7.078 MiB |
| `dvrpsim/vnsme_runs/comparison_instance2_final` | 1,698 | 6,990,035 | 6.666 MiB |
| `dvrpsim/vnsme_runs/integration_probe` | 1,682 | 5,317,676 | 5.071 MiB |
| `dvrpsim/vnsme_runs/huawei_instance2_startup_checked` | 52 | 3,447,794 | 3.288 MiB |
| `dvrpsim/vnsme_runs/huawei_instance2_final` | 52 | 3,447,656 | 3.288 MiB |
| `dvrpsim/vnsme_runs/huawei_instance2` | 51 | 3,445,058 | 3.285 MiB |
| `dvrpsim/vnsme_runs/gp_instance2` | 4 | 766,312 | 0.731 MiB |
| `dvrpsim/vnsme_runs/greedy_instance2` | 4 | 758,768 | 0.724 MiB |
| `dvrpsim/vnsme_runs/comparison_instance2` | 5 | 756,569 | 0.722 MiB |

### dvrpsim/migration_runs

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/migration_runs/reference_retry_20261108_01` | 3,116 | 154,091,370 | 146.953 MiB |
| `dvrpsim/migration_runs/vnsme_reference` | 5,897 | 80,348,232 | 76.626 MiB |
| `dvrpsim/migration_runs/vnsme_validation6` | 643 | 12,445,566 | 11.869 MiB |
| `dvrpsim/migration_runs/gp_vs_vnsme_instance2` | 1,692 | 7,518,727 | 7.170 MiB |
| `dvrpsim/migration_runs/frozen_gp_check` | 36 | 7,143,903 | 6.813 MiB |
| `dvrpsim/migration_runs/vnsme_reference_ready` | 1 | 5,091 | 0.005 MiB |

### dvrpsim/baseline_runs

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/baseline_runs/instance1_insertion_final` | 5 | 219,850 | 0.210 MiB |
| `dvrpsim/baseline_runs/instance1_insertion_repeat` | 4 | 217,113 | 0.207 MiB |
| `dvrpsim/baseline_runs/instance1_insertion_v1` | 4 | 211,112 | 0.201 MiB |
| `dvrpsim/baseline_runs/instance1_demo_final` | 10 | 125,131 | 0.119 MiB |
| `dvrpsim/baseline_runs/instance1_demo_repeat` | 9 | 122,306 | 0.117 MiB |
| `dvrpsim/baseline_runs/instance1_demo_v1` | 9 | 120,901 | 0.115 MiB |

### dvrpsim/dataset_runs

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/dataset_runs/baseline_calibration_20261105` | 32 | 1,492,633 | 1.423 MiB |

### dvrpsim/vnsme_evidence

| Path | Files | Bytes | Size |
| --- | --- | --- | --- |
| `dvrpsim/vnsme_evidence/v3_reference_supervision_20261109_r1` | 328 | 7,627,841 | 7.274 MiB |
| `dvrpsim/vnsme_evidence/scale100_blockers_20261109_r2` | 24 | 5,243,827 | 5.001 MiB |
| `dvrpsim/vnsme_evidence/scale100_contract_resolution` | 44 | 4,344,274 | 4.143 MiB |
| `dvrpsim/vnsme_evidence/v3_independent_audit_20261109_r1` | 236 | 1,345,304 | 1.283 MiB |
| `dvrpsim/vnsme_evidence/v3_instance5_recovery_20261110_r1` | 25 | 687,084 | 0.655 MiB |
| `dvrpsim/vnsme_evidence/v3_references_3_6_20261109_r1` | 10 | 626,834 | 0.598 MiB |
| `dvrpsim/vnsme_evidence/v3_references_3_6_20261109_recovery_r1` | 9 | 403,327 | 0.385 MiB |
| `dvrpsim/vnsme_evidence/fast_audit_instance5_20261110_152157` | 2 | 369,291 | 0.352 MiB |


## Nhóm có khả năng tích lũy nhanh

1. VNSME epoch diagnostics: stderr.txt 641.534 MiB / 3182 files, java_stderr_live.txt 380.486 MiB / 1347 files. Traced invocation tạo live stream rồi đọc lại để ghi stderr.txt; ba cặp lớn nhất đã hash bằng nhau. Chỉ một epoch standalone5/00062 đã có hai file tổng 95.099 MiB. Đây là yếu tố tăng dung lượng chính, không phải số source modules.
2. GP rollout copies và candidate_trace.jsonl: gp_runs 415.337 MiB; scale100 diagnostic 95.814 MiB; trace lớn nhất 10.036 MiB. Không gọi saved rollouts là cache có thể bỏ.
3. V3 supervision/decision traces và per-epoch JSON có giá trị audit; extension JSON/JSONL tổng 559.201 MiB nhưng trộn nhiều loại evidence.
4. Python bytecode 57.904 MiB; root/main venv cùng nhau 148.472 MiB. Phần lớn cache ở environment, không trong core code.

Phân bố existing run bytes theo last-modified local day (Asia/Bangkok):

| Last-modified day | Files | Bytes | Size |
| --- | --- | --- | --- |
| 2026-11-05 | 683 | 35,872,151 | 34.210 MiB |
| 2026-11-08 | 17,508 | 548,843,786 | 523.418 MiB |
| 2026-11-09 | 12,541 | 491,852,949 | 469.068 MiB |
| 2026-11-10 | 8,751 | 665,668,188 | 634.831 MiB |

Đây KHÔNG phải tốc độ tăng bytes/ngày: không có longitudinal snapshots, mtime có thể do copy/rewrite. Không dự báo dung lượng tương lai từ bảng này.

## Kiểm tra trạng thái nghiên cứu phục vụ bảo vệ

Bảy accepted v3 collections hiện còn record/result/protocol/supervision metadata. Status PASS đã được audit ở nhiệm vụ trước và được record báo lại; nhiệm vụ cleanup này không chạy replay/scorer lại. Tổng footprint 633.569 MiB. Hai instance5 khác J nên không phải duplicate run. Chưa tìm thấy combined summary v3 2–6 ở inventory; không tạo summary trong nhiệm vụ này.

GP completed v2 + audit và official incomplete được giữ. Protocol draft v3 vẫn disabled, không dùng cleanup làm cơ hội chạy trainer. Dataset/source/split metadata giữ nguyên; không kiểm sealed content.
