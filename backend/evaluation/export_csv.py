import os
import json
import csv

results_dir = os.path.join(os.path.dirname(__file__), "results")
json_path = os.path.join(results_dir, "evaluation_metrics.json")

with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# 1. Write ranking_comparison.csv
ranking_csv = os.path.join(results_dir, "ranking_comparison.csv")
with open(ranking_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Baseline", "Precision@1", "Recall@1", "nDCG@1",
        "Precision@3", "Recall@3", "nDCG@3",
        "Precision@5", "Recall@5", "nDCG@5",
        "MRR", "Avg_Latency_ms"
    ])
    for b_name, m in data["ranking_benchmarks"].items():
        writer.writerow([
            b_name,
            m["precision@1"], m["recall@1"], m["ndcg@1"],
            m["precision@3"], m["recall@3"], m["ndcg@3"],
            m["precision@5"], m["recall@5"], m["ndcg@5"],
            m["mrr"], m["avg_latency_ms"]
        ])

# 2. Write extraction_and_privacy.csv
extraction_csv = os.path.join(results_dir, "extraction_and_privacy.csv")
with open(extraction_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Category", "Metric", "Value"])
    for k, v in data["skill_extraction_ontology_mapping"].items():
        writer.writerow(["Skill_Extraction_ESCO", k, v])
    for k, v in data["privacy_evaluation"].items():
        writer.writerow(["Privacy_Preservation", k, v])
    for k, v in data["trustworthy_generation_evaluation"].items():
        writer.writerow(["Trustworthy_Generation", k, str(v)])

print(f"Exported {ranking_csv} and {extraction_csv}")
