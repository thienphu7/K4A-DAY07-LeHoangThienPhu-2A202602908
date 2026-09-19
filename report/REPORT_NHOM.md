# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** [Tên nhóm]
**Thành viên:** [Họ tên từng thành viên]
**Ngày:** [Ngày nộp]

> **Nộp 1 bản / nhóm.** Phần cá nhân (hướng tiếp cận, kết quả riêng, dự đoán…) mỗi thành viên nộp riêng trong `REPORT_CANHAN.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần nhóm: 40** = Lựa chọn tài liệu (10) + Thiết kế chiến lược (15) + Chất lượng truy xuất (10) + Thuyết trình (5).

---

## 1. Lựa chọn tài liệu (Document Set Quality) — Nhóm (10 điểm)

### Chủ đề (Domain) & Lý Do Chọn

**Chủ đề:** Quy định mượn và yêu cầu tài liệu của Thư viện University of Sydney (K4-L3A).

**Tại sao nhóm chọn chủ đề này?**
> Đây là nhóm quy định đại học công khai, có nhiều điều kiện, con số và mốc thời gian phù hợp để kiểm tra chất lượng retrieval. Nguồn chính thức cũng phân biệt người học và nhân viên trong dịch vụ Resource Sharing, nhờ đó trường `audience` tạo ra phép thử metadata filter có ý nghĩa thay vì chỉ tồn tại trên schema.

### Danh sách tài liệu (Data Inventory)

| # | Tên tài liệu | Nguồn (Source URL) | Ngày lấy / Phiên bản | Số ký tự | Metadata đã gán |
|---|--------------|------------|--------------------|----------|-----------------|
| 1 | Limits on borrowing | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/limits-on-borrowing) | 2026-09-19 / `not-stated` | 960 | `audience=all`, `category=borrowing-limits`, `department=library`, `language=en` |
| 2 | Borrowing terms and conditions | [University of Sydney Library](https://www.library.sydney.edu.au/about/governance/borrowing-terms-and-conditions) | 2026-09-19 / `not-stated` | 1.400 | `audience=all`, `category=borrowing-policy`, `department=library`, `language=en` |
| 3 | Requesting items | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/requesting-items) | 2026-09-19 / `not-stated` | 1.575 | `audience=all`, `category=requests`, `department=library`, `language=en` |
| 4 | Returning items | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/returning-items) | 2026-09-19 / `not-stated` | 1.195 | `audience=all`, `category=returns`, `department=library`, `language=en` |
| 5 | Resource sharing for eligible students | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/request-an-item-from-outside-our-library) | 2026-09-19 / `not-stated` | 1.404 | `audience=student`, `category=resource-sharing`, `department=library`, `language=en` |
| 6 | Resource sharing for staff | [University of Sydney Library](https://www.library.sydney.edu.au/support/borrowing/request-an-item-from-outside-our-library) | 2026-09-19 / `not-stated` | 1.291 | `audience=staff`, `category=resource-sharing`, `department=library`, `language=en` |

**Danh sách kiểm tra quản trị dữ liệu (Data governance checklist):**
- [x] Tập tài liệu (Corpus) chỉ chứa nguồn công khai/được phép dùng và không chứa dữ liệu cá nhân, thông tin đăng nhập hoặc tài liệu nội bộ.
- [x] Mỗi tài liệu có `source_url`, `retrieved_at`, `document_version` (hoặc ngày hiệu lực) trong metadata.

### Cấu trúc Metadata (Metadata Schema)

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho truy xuất (retrieval)? |
|----------------|------|---------------|-------------------------------|
| `doc_id` | string | `resource-sharing-students` | Định danh ổn định, duy nhất; liên kết file nguồn với chunk và dòng trong `sources.csv`. |
| `title` | string | `Resource sharing for eligible students` | Bổ sung tín hiệu ngữ nghĩa và giúp hiển thị nguồn dễ đọc. |
| `source_url` | URL string | `https://www.library.sydney.edu.au/...` | Truy vết câu trả lời về nguồn chính thức để kiểm chứng. |
| `retrieved_at` | date (`YYYY-MM-DD`) | `2026-09-19` | Cho biết thời điểm chụp dữ liệu, hữu ích khi quy định thay đổi. |
| `document_version` | string | `not-stated` | Lưu phiên bản khi nguồn công bố; dùng `not-stated` để tránh tự đặt phiên bản. |
| `audience` | enum string | `student`, `staff`, `all` | Cho phép lọc đúng đối tượng; đặc biệt tách điều kiện Resource Sharing của sinh viên và nhân viên. |
| `department` | string | `library` | Giới hạn retrieval theo đơn vị cung cấp dịch vụ khi corpus được mở rộng. |
| `category` | string | `returns`, `requests`, `resource-sharing` | Thu hẹp kết quả theo loại quy định hoặc thao tác cần tra cứu. |
| `language` | ISO-like string | `en` | Hỗ trợ chọn embedder và lọc ngôn ngữ cho corpus đa ngữ. |

---

## 2. Thiết kế chiến lược (Strategy Design) — Nhóm (15 điểm)

> Mỗi thành viên thử **một chiến lược khác nhau** trên cùng bộ tài liệu; nhóm tổng hợp và so sánh ở đây.

### Phân tích đường cơ sở (Baseline Analysis)

Chạy `ChunkingStrategyComparator().compare()` trên 2-3 tài liệu:

| Tài liệu | Chiến lược (Strategy) | Số lượng Chunk | Độ dài trung bình | Giữ được ngữ cảnh không? |
|-----------|----------|-------------|------------|-------------------|
| | FixedSizeChunker (`fixed_size`) | | | |
| | SentenceChunker (`by_sentences`) | | | |
| | RecursiveChunker (`recursive`) | | | |

### Chiến lược của từng thành viên

> Mỗi thành viên điền một khối dưới đây (copy thêm nếu nhóm có nhiều hơn 3 người).

**Thành viên 1 — [Tên]**
- **Loại chiến lược:** [FixedSize / Sentence / Recursive / custom]
- **Mô tả & lý do chọn cho chủ đề này:** *(2-3 câu)*
- **Code snippet (nếu custom):**
```python
# Dán mã nguồn (implementation) vào đây
```

**Thành viên 2 — [Tên]**
- **Loại chiến lược:**
- **Mô tả & lý do chọn:**
- **Code snippet (nếu custom):**

**Thành viên 3 — [Tên]**
- **Loại chiến lược:**
- **Mô tả & lý do chọn:**
- **Code snippet (nếu custom):**

### So Sánh Giữa Các Thành Viên

| Thành viên | Chiến lược (Strategy) | Điểm truy xuất (/10) | Điểm mạnh | Điểm yếu |
|-----------|----------|----------------------|-----------|----------|
| | | | | |
| | | | | |
| | | | | |

**Chiến lược nào tốt nhất cho chủ đề này? Tại sao?**
> *Viết 2-3 câu — đây là phần được đánh giá cao nhất (khả năng suy nghĩ & giải thích):*

---

## 3. Câu hỏi đánh giá & Chất lượng truy xuất (Retrieval Quality) — Nhóm (10 điểm)

### Câu hỏi đánh giá & Câu trả lời chuẩn (nhóm thống nhất)

> **Đúng 5 câu hỏi**, đa dạng, có thể kiểm chứng; **ít nhất 1 câu** cần lọc metadata mới trả lời tốt. Đây là bộ câu hỏi chung cho mọi thành viên chạy.

| # | Câu hỏi (Query) | Câu trả lời chuẩn (Gold Answer) | Chunk nào chứa thông tin? |
|---|-------|-------------------------------|--------------------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

### Tổng hợp chất lượng truy xuất của nhóm

> Cách chấm (theo `docs/SCORING.md`): **2 điểm/câu** — top-3 chứa chunk liên quan + agent trả lời đúng (2), có liên quan nhưng thiếu/không ở top-1 (1), không có trong top-3 (0).

| # | Câu hỏi | Chiến lược tốt nhất cho câu này | Có chunk liên quan trong top-3? | Ghi chú |
|---|---------|-------------------------------|-------------------------------|---------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

**Lọc bằng metadata có giúp ích không? Ở câu hỏi nào?**
> *Viết 2-3 câu:*

---

## 4. Thuyết trình (Demo) & Bài học nhóm — Nhóm (5 điểm)

**Những phân tích (insights) hay nhất nhóm sẽ trình bày:**
> *Liệt kê 2-3 ý:*

**Bài học rút ra khi so sánh trong nhóm:**
> *Viết 2-3 câu — cùng tài liệu nhưng chiến lược khác nhau dẫn tới khác biệt gì?*

**Nếu làm lại, nhóm sẽ thay đổi gì trong chiến lược dữ liệu (data strategy)?**
> *Viết 2-3 câu:*

---

## Tự Đánh Giá (Phần Nhóm)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Lựa chọn tài liệu (Document Set Quality) | / 10 |
| Thiết kế chiến lược (Strategy Design) | / 15 |
| Chất lượng truy xuất (Retrieval Quality) | / 10 |
| Thuyết trình (Demo) | / 5 |
| **Tổng phần nhóm** | **/ 40** |
