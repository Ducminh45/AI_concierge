import json
import os

db_path = "data/vietnam_luxury_resorts_db.json"
md_path = "data/vietnam_luxury_resorts_merged.md"
images_json_path = r"C:\Users\X1\.gemini\antigravity\brain\25820dc8-b0da-4109-b257-3c02b692ec63\scratch\vinpearl_wiki_images.json"

if not os.path.exists(images_json_path):
    print("Error: vinpearl_wiki_images.json not found!")
    exit(1)

with open(images_json_path, "r", encoding="utf-8") as f:
    images_data = json.load(f)

# Build image blocks
image_records = [
    {
        "id": "images_vinpearl_general",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Chuỗi hệ thống Vinpearl (Vinpearl Gallery)",
        "keywords": [
            "ảnh", "hình ảnh", "ảnh vinpearl", "hình ảnh vinpearl", "photos", "images", "vinpearl", "resort gallery", "xem ảnh"
        ],
        "content": (
            "Dưới đây là một số hình ảnh thực tế về chuỗi nghỉ dưỡng Vinpearl:\n"
            "• Khách sạn Vinpearl Nha Trang: ![Khách sạn Vinpearl Nha Trang](https://upload.wikimedia.org/wikipedia/commons/9/93/Vinpearl_Hotel_-_Nha_Trang.jpg)\n"
            "• Cáp treo Vinpearl Nha Trang vượt vịnh: ![Cáp treo Vinpearl](https://upload.wikimedia.org/wikipedia/commons/0/06/Vinpearl_Cable_Car_1.jpg)\n"
            "• Khu nghỉ dưỡng Vinpearl Nam Hội An: ![Vinpearl Nam Hội An](https://upload.wikimedia.org/wikipedia/commons/1/10/Vinpearl_Nam_Hoi_An_%2849374186357%29.jpg)\n"
            "• VinWonders Phú Quốc: ![VinWonders Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/c/ce/VinWonders-Phu-Quoc.jpg)"
        )
    },
    {
        "id": "images_vinpearl_phu_quoc",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Phú Quốc (Vinpearl Phu Quoc Gallery)",
        "keywords": [
            "ảnh phú quốc", "hình ảnh phú quốc", "ảnh vinpearl phú quốc", "hình ảnh vinpearl phú quốc", "photos phu quoc", "images phu quoc", "phú quốc", "phu quoc"
        ],
        "content": (
            "Dưới đây là các hình ảnh thực tế về Vinpearl Phú Quốc & VinWonders:\n"
            "• Bãi biển Vinpearl Phú Quốc: ![Bãi biển Vinpearl Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/6/63/Vinpearl_Phu_Quoc_%2849355653186%29.jpg)\n"
            "• Công viên chủ đề VinWonders Phú Quốc: ![VinWonders Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/c/ce/VinWonders-Phu-Quoc.jpg)\n"
            "• Vòng quay Ferris Wheel VinWonders Phú Quốc: ![Vòng quay Ferris Wheel Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/5/59/VinWonders_Phu_Quoc_from_ferris_wheel.jpg)\n"
            "• Hoàng hôn Vinpearl Phú Quốc: ![Hoàng hôn Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/1/16/Vinpearl_Phu_Quoc_%2849356098102%29.jpg)"
        )
    },
    {
        "id": "images_vinpearl_nha_trang",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Nha Trang (Vinpearl Nha Trang Gallery)",
        "keywords": [
            "ảnh nha trang", "hình ảnh nha trang", "ảnh vinpearl nha trang", "hình ảnh vinpearl nha trang", "photos nha trang", "images nha trang", "nha trang", "cáp treo nha trang"
        ],
        "content": (
            "Dưới đây là các hình ảnh thực tế về Vinpearl Nha Trang:\n"
            "• Toàn cảnh Vịnh Nha Trang & VinWonders: ![Toàn cảnh Vịnh Nha Trang](https://upload.wikimedia.org/wikipedia/commons/1/11/Nha_Trang_Bay_and_Vinwonders._Nha_Trang%2C_Vietnam._June_2025.jpg)\n"
            "• Khách sạn Vinpearl Nha Trang: ![Khách sạn Vinpearl Nha Trang](https://upload.wikimedia.org/wikipedia/commons/9/93/Vinpearl_Hotel_-_Nha_Trang.jpg)\n"
            "• Cáp treo vượt biển Vinpearl Nha Trang: ![Cáp treo Vinpearl Nha Trang](https://upload.wikimedia.org/wikipedia/commons/0/06/Vinpearl_Cable_Car_1.jpg)\n"
            "• Công viên nước Vinpearl Nha Trang: ![Công viên nước Vinpearl Nha Trang](https://upload.wikimedia.org/wikipedia/commons/2/27/Vinpearl_waterpark.jpg)"
        )
    },
    {
        "id": "images_vinpearl_hoi_an",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Hội An (Vinpearl Nam Hoi An Gallery)",
        "keywords": [
            "ảnh hội an", "hình ảnh hội an", "ảnh nam hội an", "hình ảnh nam hội an", "photos hoi an", "images hoi an", "hội an", "hoi an", "nam hội an", "nam hoi an"
        ],
        "content": (
            "Dưới đây là các hình ảnh thực tế về Vinpearl Nam Hội An:\n"
            "• Toàn cảnh Vinpearl Nam Hội An: ![Vinpearl Nam Hội An](https://upload.wikimedia.org/wikipedia/commons/1/10/Vinpearl_Nam_Hoi_An_%2849374186357%29.jpg)"
        )
    }
]

# Update JSON Database
with open(db_path, "r", encoding="utf-8") as f:
    db_data = json.load(f)

# Filter out old image records
db_data = [item for item in db_data if not item.get("id", "").startswith("images_")]
# Append new image records
db_data.extend(image_records)

with open(db_path, "w", encoding="utf-8") as f:
    json.dump(db_data, f, ensure_ascii=False, indent=2)
print("Successfully injected images to JSON database!")

# Update MD Database (append to vietnam_luxury_resorts_merged.md)
with open(md_path, "r", encoding="utf-8") as f:
    md_content = f.read()

# Remove old gallery section if exists
if "## 📸 Hình ảnh các Resort (Resort Gallery)" in md_content:
    md_content = md_content.split("## 📸 Hình ảnh các Resort (Resort Gallery)")[0].strip()

# Add gallery section
gallery_md = "\n\n## 📸 Hình ảnh các Resort (Resort Gallery)\n\n"
for rec in image_records:
    gallery_md += f"### {rec['item']}\n"
    gallery_md += f"**Keywords:** {', '.join(rec['keywords'])}\n\n"
    gallery_md += f"{rec['content']}\n\n"

md_content = md_content + gallery_md
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_content)
print("Successfully injected images to Markdown database!")
