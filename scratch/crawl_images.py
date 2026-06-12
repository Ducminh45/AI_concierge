import urllib.request
import json
import urllib.parse
import sys
import os

# Reconfigure stdout to use UTF-8 to prevent encoding errors on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def search_wiki_images(query):
    print(f"Searching Wikimedia Commons for: {query}")
    encoded_query = urllib.parse.quote(query)
    
    # 1. Search for files matching query
    search_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={encoded_query}&srnamespace=6&format=json"
    
    try:
        req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0 (AI Resort Concierge bot)'})
        with urllib.request.urlopen(req) as response:
            search_data = json.loads(response.read().decode('utf-8'))
            search_results = search_data.get('query', {}).get('search', [])
            
            if not search_results:
                return []
            
            # 2. Get URLs for these files
            titles = "|".join([res['title'] for res in search_results[:10]])
            encoded_titles = urllib.parse.quote(titles)
            info_url = f"https://commons.wikimedia.org/w/api.php?action=query&titles={encoded_titles}&prop=imageinfo&iiprop=url&format=json"
            
            info_req = urllib.request.Request(info_url, headers={'User-Agent': 'Mozilla/5.0 (AI Resort Concierge bot)'})
            with urllib.request.urlopen(info_req) as info_resp:
                info_data = json.loads(info_resp.read().decode('utf-8'))
                pages = info_data.get('query', {}).get('pages', {})
                
                images = []
                for page_id, page_info in pages.items():
                    imageinfo = page_info.get('imageinfo', [])
                    if imageinfo:
                        images.append({
                            'title': page_info.get('title'),
                            'url': imageinfo[0].get('url')
                        })
                return images
                
    except Exception as e:
        print(f"Error searching images for {query}: {e}")
        return []

# Test with various related Vinpearl topics
topics = [
    "Vinpearl Phu Quoc",
    "VinWonders Phu Quoc",
    "Vinpearl Nha Trang",
    "Vinpearl cable car",
    "Vinpearl Ha Tinh",
    "Vinpearl Cua Hoi",
    "Vinpearl Nam Hoi An",
    "Vinpearl Bac Ninh",
    "Vinpearl Ha Long",
    "Dao Reu",
    "Vinpearl Resort",
    "VinWonders"
]

all_images = {}
for topic in topics:
    images = search_wiki_images(topic)
    if images:
        all_images[topic] = images
        print(f"Found {len(images)} images for {topic}:")
        for img in images[:3]:
            print(f"  - {img['title']}: {img['url']}")
    else:
        print(f"No images found for {topic}")

# Save results to a json file in scratch
with open("vinpearl_wiki_images.json", "w", encoding="utf-8") as f:
    json.dump(all_images, f, ensure_ascii=False, indent=2)
print("Saved all image mappings to vinpearl_wiki_images.json")
