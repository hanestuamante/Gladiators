<!-- SINH TỰ ĐỘNG bởi scripts/render_topic_prompts.py — không sửa tay -->
<!-- topics=c1cf992e1d852a27 invariants=9439b87095d47d42 renderer=prompt-library.v1 -->

# CORE — CORE

- kind: `core`
- anchor: `ProductListing`
- kế thừa: —

## Semantic refs

```text
dim.country | dimension | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=INV-COUNTRY-COVERAGE
dim.date | dimension | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=INV-DATE-RANGE-HONOURED,INV-SNAPSHOT-SCOPE
dim.brand | dimension | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
dim.product_name | dimension | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
dim.shop_name | dimension | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
derived.product_count | derived_metric | listings | grain=group | agg=count | filters=eq,lt,lte,gt,gte | binding=exposed_as_measure | invariant=-
derived.shop_count | derived_metric | shops | grain=group | agg=count | filters=eq,lt,lte,gt,gte | binding=exposed_as_measure | invariant=-
derived.brand_count | derived_metric | brands | grain=group | agg=count | filters=eq,lt,lte,gt,gte | binding=exposed_as_measure | invariant=-
derived.category_count | derived_metric | categories | grain=group | agg=count | filters=eq,lt,lte,gt,gte | binding=exposed_as_measure | invariant=-
entity.product_listing | entity | dimension | grain=listing | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.shop | entity | dimension | grain=shop | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.brand | entity | dimension | grain=brand | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.country | entity | dimension | grain=country | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.date_snapshot | entity | dimension | grain=snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.sales_metric | entity | dimension | grain=snapshot_or_transition | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.content | entity | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.promotion_id_observation | entity | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.voucher_observation | entity | dimension | grain=listing_snapshot | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=-
entity.platform_category | entity | dimension | grain=platform_category | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=INV-SHELF-NOT-PLATFORM-CATEGORY
entity.shop_category | entity | dimension | grain=shop_category | agg=- | filters=eq,in | binding=exposed_as_dimension | invariant=INV-SHELF-NOT-PLATFORM-CATEGORY
```

## Relation paths

| path | relation | grain | fanout | dedupe |
| --- | --- | --- | --- | --- |
| `listing_by_date` | `observed_at` | listing_snapshot → listing_snapshot | none | — |

## Invariants

- `INV-SNAPSHOT-SCOPE` (hard) — `invariant.snapshot_scope`
- `INV-CURRENCY-NO-MIX` (hard) — `invariant.currency_no_mix`
- `INV-EMPTY-RESULT-IS-VALID` (hard) — `invariant.empty_result_valid`

<!-- render_budget_tokens=798 -->
