# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có | dùng trong phạm vi tone |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không | loại khỏi gate |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người | “Đã hoàn tiền” không có bằng chứng ledger; câu khẳng định không tự chứng minh giao dịch. |
| 2 | H-017 | PASS | FAIL | Người | Khoản 25.000đ cho O-606 trái điều kiện của clause hiện hành; thêm kiểm tra chính sách và ledger. |
| 3 | H-029 | PASS | FAIL | Người | “Đang xử lý” không trả lời kết quả yêu cầu; helpful cần chấm đủ thông tin và trạng thái. |
| 4 | H-042 | FAIL | PASS | Người | Hoàn 120.000đ là khoản chênh hợp lệ theo ledger; không phạt câu trả lời chỉ vì khác quote ban đầu. |
| 5 | H-051 | FAIL | PASS | Người | Câu có số tiền hợp lệ trong ngữ cảnh; yêu cầu judge đối chiếu khoản thực ghi thay vì mặc định mọi con số là sai. |

## Kết luận
- Tiêu chí bị loại và lý do (dẫn ma trận nhầm lẫn).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.

## Kết luận đã hiệu chuẩn

`tone_ok` vượt các floor (κ≥0.6, P≥0.8, R≥0.7); chỉ nên dùng cho tone, không làm cổng quyết định tiền/approval. Rogan–Gladen ước lượng tỷ lệ fail của tone là 0.300 từ tỷ lệ quan sát 0.280. `helpful` có precision 1.000 nhưng recall 0.300 và κ=0.375: nó bỏ sót 21/30 lỗi người gán, nên không được dùng làm gate. Audit trên là năm bất đồng đầu tiên trong replay; trước khi dùng judge ngoài môi trường mô phỏng cần hiệu chuẩn lại trên nhãn held-out mới.
