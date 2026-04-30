# Current Task

## Task name

Make the manual-enrichment CSV bridge robust for common Windows and Excel CSV files.

## Product boundary

This step should answer:

```text
Can the user export a worksheet, edit it in Excel or another Windows CSV tool, and import it back safely?
```

It should not answer:

```text
Should I apply?
```

SQLite remains the source of truth. The CSV remains only an editable worksheet.

## Implementation scope

This task is limited to:

```text
manual enrichment worksheet export/import
-> Excel-friendly encoding on export
-> tolerant decoding/header parsing/delimiter handling on import
```

Add:

- export with UTF-8 BOM for Excel compatibility
- import fallback decoding for common CSV encodings
- header normalization for BOM and surrounding whitespace
- delimiter tolerance for comma, semicolon, and tab
- continued safe handling of quoted multiline `manual_ui_text`

Do not add:

- parsing of Connects/member-since/avg-hourly/open-jobs fields
- enriched prospect dump generation
- OpenAI or any AI provider calls
- economics
- live network fetching
- broad refactors

## CSV contract

The worksheet shape stays exactly:

```text
job_key,url,title,manual_ui_text
```

Rules:

- only `manual_ui_text` is intended to be edited
- multiline pasted text must continue to work through normal CSV quoting
- blank `manual_ui_text` rows remain no-ops
- repeated identical imports remain no-ops
- changed text still creates a new latest enrichment version

## Export requirements

`export-enrichment-csv` should:

1. keep `newline=""`
2. write with `encoding="utf-8-sig"`
3. keep the same four worksheet columns
4. keep `manual_ui_text` blank by default
5. keep existing candidate-selection behavior

## Import requirements

`import-enrichment-csv` should accept common spreadsheet/editor variants:

- UTF-8 with BOM
- UTF-8 without BOM
- Windows-1252 / cp1252

Header validation should tolerate:

- BOM on the first header cell
- leading/trailing header whitespace

Delimiter handling should support:

- comma
- semicolon
- tab

If delimiter sniffing fails, default back to comma.

The importer may ignore extra columns, but it must still require and use:

- `job_key`
- `url`
- `title`
- `manual_ui_text`

## Acceptance criteria for this step

This step is done when:

1. export writes an Excel-friendly UTF-8-with-BOM worksheet,
2. import accepts UTF-8 BOM, plain UTF-8, and cp1252 CSV files,
3. BOM-prefixed and whitespace-padded headers still validate as `job_key,url,title,manual_ui_text`,
4. semicolon- and tab-delimited files import correctly,
5. quoted multiline `manual_ui_text` still imports correctly,
6. blank rows remain no-ops,
7. duplicate identical imports remain no-ops,
8. changed text still creates a new latest enrichment version,
9. the remaining unenriched worksheet is still generated after import,
10. the current preview, artifact-ingest, queue, queue-enrichment, and action flows keep working.
