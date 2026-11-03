import os
import zipfile

ROOT = os.path.abspath(".")
DIST_DIR = os.path.join(ROOT, "COGNIS_MEMBER_DISTRIBUTION")

packages = [
    ("COGNIS_MEMBER_1_FRONTEND_FINAL.zip", os.path.join(DIST_DIR, "MEMBER_1_FRONTEND")),
    ("COGNIS_MEMBER_2_AUTH_PRIVACY_FINAL.zip", os.path.join(DIST_DIR, "MEMBER_2_AUTH_PRIVACY")),
    ("COGNIS_MEMBER_3_JOB_MANAGEMENT_FINAL.zip", os.path.join(DIST_DIR, "MEMBER_3_JOB_MANAGEMENT")),
    ("COGNIS_MEMBER_4_AI_RAG_FINAL.zip", os.path.join(DIST_DIR, "MEMBER_4_AI_RAG")),
]

print("Creating final member ZIP archives...")

results = []

for zip_name, member_dir in packages:
    zip_path = os.path.join(ROOT, zip_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    file_count = 0
    total_uncompressed = 0
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(member_dir):
            for file in files:
                full_file_path = os.path.join(root, file)
                archive_name = os.path.relpath(full_file_path, member_dir)
                zf.write(full_file_path, archive_name)
                file_count += 1
                total_uncompressed += os.path.getsize(full_file_path)
                
    # Verify integrity
    with zipfile.ZipFile(zip_path, "r") as zf:
        bad_file = zf.testzip()
        if bad_file:
            print(f"ERROR: Corrupt file {bad_file} in {zip_name}")
        else:
            compressed_size = os.path.getsize(zip_path)
            results.append({
                "name": zip_name,
                "path": zip_path,
                "files": file_count,
                "compressed_size": compressed_size,
                "uncompressed_size": total_uncompressed,
                "status": "VALID (PASSED INTEGRITY TEST)"
            })

print("\n--- ZIP INTEGRITY VERIFICATION REPORT ---")
for r in results:
    print(f"Archive: {r['name']}")
    print(f"  Path: {r['path']}")
    print(f"  Files: {r['files']}")
    print(f"  Compressed Size: {r['compressed_size']:,} bytes ({r['compressed_size']/1024:.1f} KB)")
    print(f"  Uncompressed Size: {r['uncompressed_size']:,} bytes ({r['uncompressed_size']/1024:.1f} KB)")
    print(f"  Integrity Status: {r['status']}\n")
