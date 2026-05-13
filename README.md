# 🦠 China CDC Sentinel Hospital Surveillance Data

<p align="center">
  <img src="https://img.shields.io/badge/Source-China%20CDC-red?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0iI2ZmZiIgZD0iTTEyIDJsMy4wOSA2LjI2TDIyIDkuMjdsLTUgNC44N0wxOC4xOCAyMmwtNi4xOC0zLjI1TDUuODIgMjJsMS4xOC03Ljg2TDIgOS4yN2w2LjkxLTEuMDFMMTIgMnoiLz48L3N2Zz4=" alt="China CDC" />
  <img src="https://img.shields.io/badge/Update-Weekly-blue?style=for-the-badge&logo=githubactions&logoColor=white" alt="Weekly Update" />
  <img src="https://img.shields.io/badge/Format-CSV-brightgreen?style=for-the-badge&logo=files&logoColor=white" alt="CSV Format" />
  <img src="https://img.shields.io/badge/Pathogens-11-purple?style=for-the-badge&logo=biotech&logoColor=white" alt="11 Pathogens" />
  <img src="https://img.shields.io/badge/Coverage-2024%E2%80%932026-orange?style=for-the-badge&logo=calendar&logoColor=white" alt="Coverage" />
</p>

<p align="center">
  <em>Automated weekly extraction of respiratory disease surveillance data from China CDC sentinel hospitals — curated for epidemiological research and forecasting.</em>
</p>

---

## 🔁 Data Pipeline

```mermaid
flowchart LR
    A([🌐 China CDC<br/>Website]):::source -->|crawl links| B[🔗 New URL<br/>Discovery]:::step
    B -->|render page| C[📄 PDF<br/>Snapshot]:::step
    C -->|MinerU OCR| D[📝 Markdown<br/>Document]:::step
    D -->|LLM extract| E[📊 Structured<br/>CSV Records]:::step
    E -->|dedup + merge| F[(💾 Main<br/>Datasets)]:::store
    F -->|auto commit| G([🚀 GitHub<br/>Release]):::output

    classDef source fill:#ffe0e0,stroke:#d32f2f,stroke-width:2px,color:#000
    classDef step fill:#e3f2fd,stroke:#1976d2,stroke-width:2px,color:#000
    classDef store fill:#fff8e1,stroke:#f57c00,stroke-width:2px,color:#000
    classDef output fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#000
```

> Orchestrated by **Apache Airflow** — runs every **Friday at 00:00** (Asia/Shanghai) and only commits when new reports are detected.

---

## ✨ Highlights

- 🔄 **Fully automated** — weekly cron schedule via Airflow DAG, zero manual intervention
- 🧬 **11 pathogens tracked** — including SARS-CoV-2, Influenza A/B, RSV, hMPV, RV, and more
- 📅 **Long-term coverage** — continuous weekly records from **Nov 2024** to present
- 🏥 **Two clinical settings** — outpatient ILI (流感样病例) and inpatient SARI (严重急性呼吸道感染)
- 🎯 **Forecast-ready format** — drop-in compatible with [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub)
- 🗂️ **Full provenance** — every weekly update preserves the original PDF, Markdown, and extracted CSV under `update/<date>/`

---

## 📊 Datasets

### 1️⃣ COVID-19 Focus — `data/cncdc_surveillance_covid19.csv`

Weekly SARS-CoV-2 positivity rates, formatted for the [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub) project.

| Column            | Type   | Description                                |
| ----------------- | ------ | ------------------------------------------ |
| `reference_date`  | date   | Surveillance week start (Monday)           |
| `target_end_date` | date   | Surveillance week end (Sunday)             |
| `report_week`     | int    | ISO week number                            |
| `pathogen`        | string | Pathogen name (`新型冠状病毒` / SARS-CoV-2) |
| `ili_percent`     | float  | Outpatient ILI positive rate (%)           |
| `sari_percent`    | float  | Inpatient SARI positive rate (%)           |

### 2️⃣ Multi-Pathogen — `data/cncdc_surveillance_all.csv`

Full multi-pathogen surveillance panel with identical schema, covering all 11 monitored respiratory pathogens.

### 3️⃣ Historical Gap — `data/cncdc_suverillance_2025_14_22.csv`

COVID-19-only records reconstructed from monthly China CDC reports for **2025 weeks 14–22**, when weekly surveillance bulletins were temporarily replaced by monthly summaries.

---

## 🧬 Pathogens Monitored

| Chinese name       | English / Scientific name             |
| ------------------ | ------------------------------------- |
| 新型冠状病毒        | SARS-CoV-2                            |
| 流感病毒            | Influenza virus (A & B)               |
| 呼吸道合胞病毒      | Respiratory Syncytial Virus (RSV)     |
| 人偏肺病毒          | Human Metapneumovirus (hMPV)          |
| 副流感病毒          | Parainfluenza virus (PIV)             |
| 普通冠状病毒        | Common human coronaviruses (HCoV)     |
| 腺病毒              | Adenovirus                            |
| 博卡病毒            | Bocavirus                             |
| 鼻病毒              | Rhinovirus                            |
| 肠道病毒            | Enterovirus                           |
| 肺炎支原体          | *Mycoplasma pneumoniae*               |

---

## 📁 Repository Layout

```text
cn_cdc_data/
├── data/
│   ├── cncdc_surveillance_covid19.csv      # COVID-19 weekly series
│   ├── cncdc_surveillance_all.csv          # All 11 pathogens
│   └── cncdc_suverillance_2025_14_22.csv   # Historical gap (W14–W22 2025)
└── update/
    └── YYYY-MM-DD/                         # One folder per weekly report
        ├── pdf/                            # Original page snapshot
        ├── md/                             # OCR'd markdown
        └── csv/                            # Extracted weekly records
```

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/dailypartita/cn_cdc_crawl.git
cd cn_cdc_crawl

# Load the data in Python
python - <<'EOF'
import pandas as pd
covid = pd.read_csv("data/cncdc_surveillance_covid19.csv")
print(covid.head())
print(f"Latest week: {covid['reference_date'].max()}  |  records: {len(covid)}")
EOF
```

Or load directly from GitHub:

```python
import pandas as pd

URL = "https://raw.githubusercontent.com/dailypartita/cn_cdc_crawl/main/data/cncdc_surveillance_covid19.csv"
df = pd.read_csv(URL)
```

---

## ⚠️ Notes & Caveats

- **2025 Weeks 14–22 gap** — During this period the China CDC published only monthly aggregated reports. Recovered COVID-19 data is provided separately in `data/cncdc_suverillance_2025_14_22.csv`; other pathogens are not available for these weeks.
- **Reporting basis** — Rates reflect *positivity among sampled patients at sentinel hospitals*, not population incidence.
- **Late revisions** — China CDC occasionally retroactively revises prior weeks; the pipeline deduplicates by `(reference_date, pathogen)` and keeps the most recent value.

---

## 📚 Data Source

Official surveillance bulletins from the **Chinese Center for Disease Control and Prevention (China CDC)**:

🔗 <https://www.chinacdc.cn/jksj/jksj04_14275/>

---

## 📬 Contact

**Kaixin Yang** — `yang_kaixin@gzlab.ac.cn`
Guangzhou Laboratory · Computational Epidemiology Group

---

## ⚖️ Disclaimer

This dataset is redistributed for **non-commercial research and analytical purposes**. All original data remains the intellectual property of the Chinese Center for Disease Control and Prevention. Users are responsible for verifying data fitness for their specific use case and for citing the original source.
