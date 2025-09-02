# ============ surveillance ============

# uv run save_web_to_pdf.py \
#     url_surveillance.txt -o pdf_surveillance \
#     --format A1 --margin 10mm \
#     -c 6 --wait-until load

# uv run convert_pdf_to_md.py pdf_surveillance -o md_surveillance \
#   --server http://10.22.16.132:8011 \
#   --lang ch --backend pipeline --parse-method auto \
#   --formula-enable true --table-enable true \
#   --workers 6 --timeout 180 

# export OPENROUTER_API_KEY="sk-or-********"
# uv run python extract_data_from_md.py md_surveillance -o cn_cdc_surveillance.csv --no-llm --debug

# ============ covid19 ============

# uv run save_web_to_pdf.py \
#     url_covid19.txt -o pdf_covid19 \
#     --format A1 --margin 10mm \
#     -c 6 --wait-until load

# uv run convert_pdf_to_md.py pdf_covid19 -o md_covid19 \
#   --server http://10.22.16.132:8011 \
#   --lang ch --backend pipeline --parse-method auto \
#   --formula-enable true --table-enable true \
#   --workers 6 --timeout 180 

