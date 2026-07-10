# Research Plan & Insight Notebook Guide

File này dùng để đào sâu insight từ dataset Shopee 2 thị trường `vn` và `id`. Mục tiêu không chỉ là hỏi “yếu tố nào quyết định doanh thu”, mà còn biến dataset thành một câu chuyện phân tích có cấu trúc: thị trường khác nhau ra sao, shop vận hành thế nào, category/voucher/giá ảnh hưởng thế nào, và có thể đề xuất hành động gì.

## 1. Câu hỏi nghiên cứu trung tâm

**Các yếu tố về giá, khuyến mãi, uy tín shop, danh mục, hình ảnh và nội dung sản phẩm ảnh hưởng như thế nào đến doanh thu ước tính trên Shopee, và các yếu tố này khác nhau ra sao giữa Việt Nam và Indonesia?**

Trong dataset này không có cột doanh thu thật. Vì vậy dùng chỉ số ước tính:

```text
estimated_recent_revenue = price * monthly_sold_value
```

Lưu ý:

- `price` được hiểu là giá cuối hiển thị sau khi đã phản ánh voucher/promo trong dataset.
- `monthly_sold_value` là lượt bán gần đây/theo tháng hiển thị bởi Shopee, không khẳng định chính xác là bao nhiêu ngày.
- Đây là doanh thu ước tính gần đây, không phải doanh thu kế toán chính thức.

## 2. Nhóm câu hỏi nên trả lời

### 2.1. So sánh thị trường Việt Nam và Indonesia

Mục tiêu: biết hai thị trường khác nhau ở đâu để không dùng một chiến lược chung cho cả hai.

Câu hỏi:

- Quốc gia nào có doanh thu ước tính cao hơn?
- Giá trung bình/median của sản phẩm ở `vn` và `id` khác nhau thế nào?
- Lượt bán gần đây (`monthly_sold_value`) khác nhau ra sao?
- Rating sản phẩm và rating shop ở hai nước có khác biệt không?
- Tỷ lệ sản phẩm có voucher/promo ở hai nước khác nhau thế nào?
- Nước nào phụ thuộc nhiều hơn vào discount/voucher?

Giả thuyết:

- H1: `vn` và `id` có cấu trúc giá và mức bán khác nhau.
- H2: Hiệu quả khuyến mãi không giống nhau giữa hai nước.
- H3: Một yếu tố có tác động tốt ở nước này chưa chắc tối ưu ở nước kia.

Biểu đồ nên vẽ:

- Bar chart doanh thu ước tính theo quốc gia.
- Boxplot `price` theo quốc gia.
- Boxplot `monthly_sold_value` theo quốc gia.
- Bar chart tỷ lệ sản phẩm có voucher/promo theo quốc gia.

### 2.2. Yếu tố nào liên quan mạnh tới doanh thu?

Mục tiêu: tìm các feature có quan hệ rõ nhất với `estimated_recent_revenue`.

Câu hỏi:

- `price`, `discount_percent`, `rating`, `rating_count`, `liked_count`, `images_count`, `shop_follower_count` có liên quan thế nào với doanh thu ước tính?
- Yếu tố nào có tương quan cao nhất với `monthly_sold_value`?
- Sản phẩm rating cao có luôn bán tốt hơn không?
- Lượt thích (`liked_count`) có phải tín hiệu tốt cho doanh số không?

Giả thuyết:

- H4: `rating_count` và `liked_count` có tương quan dương với doanh thu vì phản ánh social proof.
- H5: `price` có quan hệ phi tuyến với doanh thu; giá quá cao có thể giảm lượng bán.
- H6: `images_count` có thể liên quan tích cực tới doanh thu vì sản phẩm được trình bày đầy đủ hơn.

Biểu đồ nên vẽ:

- Correlation heatmap.
- Scatter `price` vs `monthly_sold_value`.
- Scatter `liked_count` vs `monthly_sold_value`.
- Scatter `rating_count` vs `estimated_recent_revenue`.

### 2.3. Chương trình khuyến mãi/voucher có hiệu quả không?

Mục tiêu: xem sản phẩm có voucher/promo có bán tốt hơn không, và mức giảm nào hợp lý.

Câu hỏi:

- Sản phẩm có voucher có `monthly_sold_value` cao hơn sản phẩm không có voucher không?
- Sản phẩm có promo có doanh thu ước tính cao hơn không?
- Nhóm vừa có voucher vừa có promo có tốt hơn nhóm chỉ có một trong hai không?
- Discount bao nhiêu là tối ưu: thấp, trung bình, hay cao?
- Voucher min spend thường nằm ở mức nào và có khác giữa `vn`/`id` không?

Giả thuyết:

- H7: Sản phẩm có voucher/promo có lượt bán cao hơn nhóm không có ưu đãi.
- H8: Discount quá cao chưa chắc làm doanh thu cao hơn, vì có thể đi kèm sản phẩm yếu hoặc biên lợi nhuận thấp.
- H9: Tác động của voucher mạnh hơn ở một thị trường so với thị trường còn lại.

Biểu đồ nên vẽ:

- Boxplot `monthly_sold_value` theo nhóm `promo_group`.
- Bar chart doanh thu ước tính trung bình theo `promo_group`.
- Bar chart theo bucket `discount_percent`.
- So sánh voucher/promo theo quốc gia.

### 2.4. Shop trust và vận hành shop ảnh hưởng thế nào?

Mục tiêu: xem độ uy tín shop có giúp sản phẩm bán tốt hơn không.

Câu hỏi:

- Official shop có doanh thu ước tính cao hơn non-official shop không?
- `shop_follower_count` có liên quan tới doanh thu không?
- `shop_rating_star` có liên quan tới doanh thu không?
- Response rate/time có ảnh hưởng đến performance không?
- Shop lớn có cần discount cao hơn/ít hơn shop nhỏ không?

Giả thuyết:

- H10: Official shop và shop có follower cao có doanh thu ước tính cao hơn.
- H11: Shop rating cao giúp tăng conversion, nhưng có thể tác động yếu hơn giá/voucher.
- H12: Follower count có thể là proxy cho brand power.

Biểu đồ nên vẽ:

- Bar chart doanh thu theo `shop_is_official_shop`.
- Scatter `shop_follower_count` vs `estimated_recent_revenue`.
- Top shop theo doanh thu ước tính.

### 2.5. Category và cách trưng bày sản phẩm

Mục tiêu: hiểu doanh thu đến từ ngành hàng nào và “kệ hàng” nội bộ nào.

Câu hỏi:

- Category nền tảng nào tạo doanh thu ước tính cao nhất?
- Danh mục nội bộ shop nào tạo nhiều lượt bán nhất?
- Sản phẩm nằm trong nhiều danh mục nội bộ có bán tốt hơn không?
- Các danh mục có tên như `Combo`, `Best Seller`, `Khuyến mãi`, `Flash Sale` có hiệu quả hơn không?
- Cách sắp xếp category giữa `vn` và `id` có khác nhau không?

Giả thuyết:

- H13: Các category có tính bundle/combo/promotion có doanh thu ước tính cao hơn category thường.
- H14: Sản phẩm được đưa vào nhiều danh mục nội bộ có cơ hội tiếp xúc cao hơn nên bán tốt hơn.
- H15: Category nền tảng giúp so sánh công bằng giữa shop, còn category nội bộ giúp hiểu chiến lược trưng bày của shop.

Biểu đồ nên vẽ:

- Top category/platform theo doanh thu ước tính.
- Top `shop_category_names` theo doanh thu ước tính.
- Boxplot doanh thu theo `shop_category_count`.

### 2.6. Hình ảnh và nội dung sản phẩm

Mục tiêu: xem presentation của listing có liên quan tới performance không.

Câu hỏi:

- Sản phẩm có nhiều ảnh hơn có bán tốt hơn không?
- Tên sản phẩm dài hơn có bán tốt hơn không?
- Tên chứa keyword `combo`, `official`, `sale`, `new`, `best seller`, `khuyến mãi` có khác biệt không?
- Sản phẩm có brand rõ ràng bán tốt hơn không?

Giả thuyết:

- H16: `images_count` cao hơn có thể liên quan tới doanh thu cao hơn.
- H17: Keyword như `combo` hoặc `official` có thể giúp sản phẩm có performance tốt hơn.
- H18: Brand rõ ràng giúp tăng trust.

Biểu đồ nên vẽ:

- Scatter/boxplot `images_count` vs `monthly_sold_value`.
- Bar chart performance theo keyword flags.
- So sánh sản phẩm có brand vs không có brand.

## 3. Framework insight đề xuất

Khi viết kết luận, nên đi theo thứ tự:

1. **Market context**: VN và ID khác nhau thế nào.
2. **Revenue drivers**: yếu tố nào liên quan mạnh tới doanh thu ước tính.
3. **Promotion effectiveness**: voucher/promo có hiệu quả không, hiệu quả ở nhóm nào.
4. **Shop/category strategy**: shop trust, category, trưng bày ảnh hưởng ra sao.
5. **Optimization recommendations**: nên tối ưu gì trước.

## 4. Câu hỏi cuối cùng nên trả lời trong báo cáo

Các câu hỏi nên xuất hiện trong report cuối:

- Thị trường `vn` và `id` khác nhau rõ nhất ở điểm nào?
- Doanh thu ước tính tập trung ở nhóm sản phẩm/shop/category nào?
- Giá và discount có quan hệ như thế nào với lượt bán?
- Voucher/promo có thật sự đi kèm hiệu quả bán hàng cao hơn không?
- Official shop/follower/rating có tạo lợi thế không?
- Category nội bộ của shop có cho thấy chiến lược trưng bày nào hiệu quả không?
- Nếu phải tối ưu để tăng doanh thu, nên ưu tiên giá, voucher, ảnh, category hay shop trust?

## 5. Notebook đi kèm

Notebook `research.ipynb` được tạo để vẽ biểu đồ kiểm tra các giả thuyết trên. Notebook đọc file:

```text
Dataset/DataProcessed/product_dataset_ready.csv
```

Các chart chính trong notebook:

- Doanh thu ước tính theo quốc gia.
- Phân phối giá và lượt bán theo quốc gia.
- Hiệu quả voucher/promo.
- Correlation heatmap các feature chính.
- Top shop/category theo doanh thu ước tính.
- Quan hệ hình ảnh/rating/liked count với doanh thu.
