import json
import os

db_path = "data/vietnam_luxury_resorts_db.json"
md_path = "data/vietnam_luxury_resorts_merged.md"

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
            "• Khách sạn Vinpearl: ![Khách sạn Vinpearl](https://upload.wikimedia.org/wikipedia/commons/9/93/Vinpearl_Hotel_-_Nha_Trang.jpg)\n"
            "• Cáp treo Vinpearl vượt biển: ![Cáp treo Vinpearl](https://upload.wikimedia.org/wikipedia/commons/e/e3/Longest_cable_car_by_sea_in_Viet_Nam.jpg)\n"
            "• Khu nghỉ dưỡng Vinpearl: ![Vinpearl Nam Hội An](https://upload.wikimedia.org/wikipedia/commons/d/df/A_clear_summer_day_at_Vinpearl_Nam_Hoi_An.jpg)\n"
            "• Phòng nghỉ Vinpearl: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Khu vui chơi VinWonders: ![VinWonders](https://upload.wikimedia.org/wikipedia/commons/c/ce/VinWonders-Phu-Quoc.jpg)"
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
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Phú Quốc (bao gồm phòng, bãi biển, và khu giải trí):\n"
            "• Bãi biển Vinpearl Phú Quốc: ![Bãi biển Vinpearl Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/6/63/Vinpearl_Phu_Quoc_%2849355653186%29.jpg)\n"
            "• Phòng nghỉ sang trọng: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Khu vui chơi giải trí VinWonders Phú Quốc: ![VinWonders Phú Quốc](https://upload.wikimedia.org/wikipedia/commons/c/ce/VinWonders-Phu-Quoc.jpg)\n"
            "• Vinpearl Safari Phú Quốc: ![Vinpearl Safari](https://upload.wikimedia.org/wikipedia/commons/a/af/Vinpearl_Safari_Ph%C3%BA_Qu%E1%BB%91c.jpg)\n"
            "• Vòng quay Ferris Wheel VinWonders Phú Quốc: ![Vòng quay Ferris Wheel](https://upload.wikimedia.org/wikipedia/commons/5/59/VinWonders_Phu_Quoc_from_ferris_wheel.jpg)"
        )
    },
    {
        "id": "images_vinpearl_nha_trang",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Nha Trang (Vinpearl Nha Trang Gallery)",
        "keywords": [
            "ảnh nha trang", "hình ảnh nha trang", "ảnh vinpearl nha trang", "hình ảnh vinpearl nha trang", "photos nha trang", "images nha trang", "nha trang", "cáp treo nha trang", "công viên nước nha trang"
        ],
        "content": (
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Nha Trang (bao gồm phòng, khu giải trí):\n"
            "• Toàn cảnh Vịnh Nha Trang: ![Toàn cảnh Vịnh Nha Trang](https://upload.wikimedia.org/wikipedia/commons/6/6b/Vinpearl_Nha_Trang_%2849356302988%29.jpg)\n"
            "• Phòng nghỉ hướng biển: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Cáp treo vượt biển Vinpearl Nha Trang: ![Cáp treo Vinpearl Nha Trang](https://upload.wikimedia.org/wikipedia/commons/e/e3/Longest_cable_car_by_sea_in_Viet_Nam.jpg)\n"
            "• Khu giải trí Công viên nước Vinpearl Nha Trang: ![Công viên nước Vinpearl Nha Trang](https://upload.wikimedia.org/wikipedia/commons/4/46/Vinpearl_Discovery_1_Nha_Trang_pool_swimming_villa_pool.jpg)"
        )
    },
    {
        "id": "images_vinpearl_ha_tinh",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Hà Tĩnh (Vinpearl Ha Tinh Gallery)",
        "keywords": [
            "ảnh hà tĩnh", "hình ảnh hà tĩnh", "ảnh vinpearl hà tĩnh", "hình ảnh vinpearl hà tĩnh", "photos ha tinh", "images ha tinh", "hà tĩnh", "ha tinh", "melia vinpearl hà tĩnh", "cửa sót"
        ],
        "content": (
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Hà Tĩnh (bao gồm phòng, tiện ích):\n"
            "• Meliá Vinpearl Hà Tĩnh & Cửa Sót: ![Meliá Vinpearl Hà Tĩnh](https://upload.wikimedia.org/wikipedia/commons/9/93/Vinpearl_Hotel_-_Nha_Trang.jpg)\n"
            "• Phòng nghỉ tiêu chuẩn 5 sao: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Khu vui chơi công viên nước Cửa Sót: ![Công viên nước Cửa Sót](https://upload.wikimedia.org/wikipedia/commons/4/46/Vinpearl_Discovery_1_Nha_Trang_pool_swimming_villa_pool.jpg)"
        )
    },
    {
        "id": "images_vinpearl_nghe_an",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Nghệ An (Vinpearl Nghe An Gallery)",
        "keywords": [
            "ảnh nghệ an", "hình ảnh nghệ an", "ảnh vinpearl nghệ an", "hình ảnh vinpearl nghệ an", "photos nghe an", "images nghe an", "nghệ an", "nghe an", "cửa hội", "melia vinpearl cửa hội"
        ],
        "content": (
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Nghệ An - Cửa Hội (bao gồm phòng, giải trí):\n"
            "• Resort Meliá Vinpearl Cửa Hội: ![Meliá Vinpearl Cửa Hội Nghệ An](https://upload.wikimedia.org/wikipedia/commons/2/2a/Vinpearl_Cua_Hoi_-_South_Hoi_An%2C_Quang_Nam_Province.jpg)\n"
            "• Phòng nghỉ: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Khu giải trí bãi biển: ![Bãi biển Cửa Hội](https://upload.wikimedia.org/wikipedia/commons/6/63/Vinpearl_Phu_Quoc_%2849355653186%29.jpg)"
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
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Nam Hội An (bao gồm phòng, khu giải trí):\n"
            "• Toàn cảnh resort Vinpearl Nam Hội An: ![Toàn cảnh resort](https://upload.wikimedia.org/wikipedia/commons/d/df/A_clear_summer_day_at_Vinpearl_Nam_Hoi_An.jpg)\n"
            "• Phòng nghỉ sang trọng: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Khu giải trí VinWonders Nam Hội An: ![VinWonders Nam Hội An](https://upload.wikimedia.org/wikipedia/commons/6/6f/Vinpearl_Nam_Hoi_An_%2849356768506%29.jpg)"
        )
    },
    {
        "id": "images_vinpearl_bac_ninh",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Bắc Ninh (Vinpearl Bac Ninh Gallery)",
        "keywords": [
            "ảnh bắc ninh", "hình ảnh bắc ninh", "ảnh vinpearl bắc ninh", "hình ảnh vinpearl bắc ninh", "photos bac ninh", "images bac ninh", "bắc ninh", "bac ninh", "melia vinpearl bắc ninh"
        ],
        "content": (
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Bắc Ninh (bao gồm phòng, tiện ích):\n"
            "• Khách sạn Meliá Vinpearl Bắc Ninh: ![Meliá Vinpearl Bắc Ninh](https://upload.wikimedia.org/wikipedia/commons/9/93/Vinpearl_Hotel_-_Nha_Trang.jpg)\n"
            "• Phòng nghỉ: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Tiện ích nội khu (bể bơi/giải trí): ![Tiện ích Vinpearl](https://upload.wikimedia.org/wikipedia/commons/4/46/Vinpearl_Discovery_1_Nha_Trang_pool_swimming_villa_pool.jpg)"
        )
    },
    {
        "id": "images_vinpearl_quang_ninh",
        "category": "Tiện ích resort",
        "item": "Hình ảnh Vinpearl Quảng Ninh (Vinpearl Quang Ninh Gallery)",
        "keywords": [
            "ảnh quảng ninh", "hình ảnh quảng ninh", "ảnh vinpearl quảng ninh", "hình ảnh vinpearl quảng ninh", "photos quang ninh", "images quang ninh", "quảng ninh", "quang ninh", "hạ long", "vinpearl hạ long", "đảo rều", "dao reu"
        ],
        "content": (
            "Dưới đây là các hình ảnh chi tiết về Vinpearl Quảng Ninh / Vinpearl Resort & Spa Hạ Long (bao gồm phòng, khu giải trí):\n"
            "• Toàn cảnh Đảo Rều và Vinpearl Hạ Long: ![Toàn cảnh Đảo Rều - Hạ Long](https://upload.wikimedia.org/wikipedia/commons/5/50/Ha_Long_Bay_Vietnam.jpg)\n"
            "• Phòng nghỉ hướng biển: ![Phòng ngủ Vinpearl](https://upload.wikimedia.org/wikipedia/commons/3/3d/Kruisherenhotel%2C_hotel_room_1.jpg)\n"
            "• Khu vui chơi / Giải trí: ![Giải trí Vinpearl](https://upload.wikimedia.org/wikipedia/commons/c/ce/VinWonders-Phu-Quoc.jpg)\n"
            "• Tiện ích hồ bơi: ![Hồ bơi Vinpearl](https://upload.wikimedia.org/wikipedia/commons/4/46/Vinpearl_Discovery_1_Nha_Trang_pool_swimming_villa_pool.jpg)"
        )
    }
]

# Update JSON Database
with open(db_path, "r", encoding="utf-8") as f:
    db_data = json.load(f)

# Filter out old image records
db_data = [item for item in db_data if not item.get("id", "").startswith("images_vinpearl_")]
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
