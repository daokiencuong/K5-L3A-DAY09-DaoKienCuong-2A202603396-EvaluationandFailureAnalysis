# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case đã phân tích: `seeded_regression C-002@55`

- **Trial:** `seeded_regression C-002@55`, eval set v1 `782535157bc0`.
- **Triệu chứng:** Lab 8 grader báo `status resolved != denied`; agent ghi hoàn 20.000đ dù label yêu cầu 0đ.
- **Bước sai đầu tiên:** event 3 `model_override`, payload `delay_days=5`. Event 2 vừa đọc DB và cho thấy order O-202 trễ 2 ngày; ticket không được ghi đè fact này.
- **Vì sao là bước đầu tiên:** handoff và investigator trước event 3 đều thuộc luồng đọc; quote 20.000đ, refund history và reply 20.000đ là hệ quả sau override.
- **Failure mode:** FM-03 (`ticket_trust`).
- **Đối chứng:** `fixed C-002@55` không có event `model_override`; quote bằng 0, không có refund, status `denied`, Lab 8 grader pass.
- **Regression test:** `test_lab9_trace_regression.py::test_ticket_override_is_first_bad_event`; test xác nhận `seeded_regression` có override và `fixed` không có.
- **Giới hạn:** trace chứng minh lỗi ở replay MockLLM/seed này; không đo tần suất trên model hoặc traffic thật.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
