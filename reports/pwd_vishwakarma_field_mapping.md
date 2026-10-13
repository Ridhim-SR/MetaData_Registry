# Field mapping report — pwd_vishwakarma

- Generated: 2026-10-07 09:55 UTC
- Submission: ..\Datasets\pwd_vishwakarma_full_raw_columns.txt
- Catalog: local registry (excluding public_works_department)

## Headline

- Fields: **213** in 1 table(s)
- Map to an existing field: **1** (0%)
- Candidates needing confirmation: **12**
- New fields: **200**
- Missing `business_description` on the submission: **213**
- Missing `tag` on the submission: **213**

## Notes
- This file is byte-identical to table public_works_department.vishwakarma.public.vishwakarma_T, which is already registered in the catalog OpenMetadata instance (213 of 213 fields present there, names and order unchanged). --catalog was set to the local registry with public_works_department excluded, so 'new' below means 'not seen from another department', not 'absent from the catalog'.
- A raw column list carries no business descriptions or tags: all 213 fields are reported missing both. Tags are assigned by the auto-tagger at ingest (109 of 213 at last local publish: Financial 71, Status/Workflow 18, Date/Timestamp 11, Geospatial 5, Firm/Contractor 4); business_description has to come from the department.

## By department

| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| public_works_department | 1 | 213 | 1 | 12 | 200 | 213 | 213 |

## Candidates to confirm

- `vishwakarma_T.cancel_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.demand_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.surrender_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.uc_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.firm_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `vishwakarma_T.form16_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.cmdash_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.prahari_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `vishwakarma_T.bidder_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `vishwakarma_T.tender_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.location_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `vishwakarma_T.work_start_date` ~ `agriculture_department.distribution_record_dataset.online_booking.start_date` (token-overlap)

## Needs fixing before ingest

- `vishwakarma_T.dist_code`: length 100 != existing None
