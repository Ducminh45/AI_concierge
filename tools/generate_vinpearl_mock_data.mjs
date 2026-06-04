import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");

const sourcePath = path.join(root, "data.txt");
const dataDir = path.join(root, "data");
const knowledgeDir = path.join(dataDir, "knowledge");
const finetuneDir = path.join(dataDir, "finetune");

const systemPrompt =
  "You are the Vinpearl AI Concierge, a warm, professional bilingual assistant for Vinpearl and Melia Vinpearl properties in Vietnam. Answer in the guest's language, use only verified resort knowledge, be concise, and offer to connect a human concierge when information is missing.";

function parseDestinations() {
  const source = fs.readFileSync(sourcePath, "utf8");
  const start = source.indexOf("export const vinpearlDestinations");
  if (start === -1) {
    throw new Error("Cannot find export const vinpearlDestinations in data.txt");
  }

  const expression = source
    .slice(start)
    .replace(/^export const vinpearlDestinations[^=]*=/, "")
    .replace(/;\s*$/, "");

  return Function(`return ${expression}`)();
}

function clean(text) {
  return String(text)
    .replace(/\[web:\d+\]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function money(value) {
  return new Intl.NumberFormat("vi-VN").format(value) + " VND";
}

function list(items, prefix = "- ") {
  return items.map((item) => `${prefix}${clean(item)}`).join("\n");
}

function destinationHeader(destination) {
  return `${destination.name}\nID: ${destination.id}\nLocation: ${destination.location}\nTags: ${destination.tags.join(", ")}\nKeywords: ${destination.keywords.join(", ")}`;
}

function write(filePath, content) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content.trimEnd() + "\n", "utf8");
}

function buildOverview(destinations) {
  const lines = [
    "VINPEARL AI CONCIERGE KNOWLEDGE BASE - DESTINATION OVERVIEW",
    "",
    "This mock dataset is generated from data.txt and is intended for retrieval, evaluation, and fine-tuning of the Vinpearl chatbot agent.",
    "Assistant rule: answer in the guest's language, stay inside the verified context, and do not invent live availability, promotions, phone numbers, or booking confirmation details.",
    "",
    "Covered properties:",
  ];

  destinations.forEach((d, index) => {
    lines.push(`${index + 1}. ${d.name} - ${d.location}`);
  });

  destinations.forEach((d) => {
    lines.push(
      "",
      "============================================================",
      destinationHeader(d),
      "",
      `Overview: ${clean(d.description)}`,
      "",
      "Best for:",
      list(d.suitableFor),
      "",
      "Highlights:",
      list(d.highlights),
      "",
      `Reference price range: ${money(d.priceRange.perNightFrom)} - ${money(d.priceRange.perNightTo)} per night. ${clean(d.priceRange.description)}`,
      `Guest rating reference: ${d.rating.average}/${d.rating.scale}. ${clean(d.rating.description)} Sources: ${d.rating.sources.join(", ")}.`
    );
  });

  return lines.join("\n");
}

function buildAmenities(destinations) {
  const lines = ["VINPEARL AMENITIES, ROOMS, DINING, AND ENTERTAINMENT"];

  destinations.forEach((d) => {
    lines.push(
      "",
      "============================================================",
      destinationHeader(d),
      "",
      `Accommodation: ${clean(d.accommodation)}`,
      "",
      `Dining: ${clean(d.dining)}`,
      "",
      `Entertainment and facilities: ${clean(d.entertainment)}`
    );
  });

  return lines.join("\n");
}

function buildPolicies(destinations) {
  const lines = [
    "VINPEARL POLICIES AND IMPORTANT NOTES",
    "",
    "General guidance: exact fees, child surcharges, inclusions, and promotions can change by room type, booking channel, and date. When the retrieved context does not answer a detail, the assistant should ask a human concierge or reservation team to verify.",
  ];

  destinations.forEach((d) => {
    lines.push(
      "",
      "============================================================",
      destinationHeader(d),
      "",
      "Policies:",
      list(d.policies),
      "",
      "Important guest notes:",
      list(d.importantNotes)
    );
  });

  return lines.join("\n");
}

function buildTransport(destinations) {
  const lines = ["VINPEARL TRANSPORTATION AND LOCAL ACCESS"];

  destinations.forEach((d) => {
    lines.push(
      "",
      "============================================================",
      destinationHeader(d),
      "",
      `How to get there: ${clean(d.transportation)}`
    );
  });

  lines.push(
    "",
    "Shared concierge transfer mock catalog:",
    "- Airport or city transfer can be requested through the concierge chat. The assistant must collect guest name, property, pickup point, destination, date, time, passenger count, luggage count, and preferred vehicle before confirming a request.",
    "- Private sedan reference: 600,000-1,200,000 VND per way depending on city distance.",
    "- MPV or family van reference: 900,000-1,800,000 VND per way depending on city distance.",
    "- Resort shuttle or VinBus availability must be verified for the specific property and booking package."
  );

  return lines.join("\n");
}

function buildServices(destinations) {
  const lines = [
    "VINPEARL CONCIERGE SERVICE MOCK CATALOG",
    "",
    "Use this file for service-request conversations. The assistant can draft a request but should not claim final confirmation until staff approval.",
    "",
    "In-room amenities:",
    "- Extra towels, pillows, blankets, slippers, bottled water, tea or coffee bags, dental kits, shaving kits, sewing kits. Mock SLA: deliver within 15-20 minutes when available.",
    "",
    "Room service:",
    "- Breakfast items: 06:00-11:00.",
    "- All-day dining: 11:00-22:00.",
    "- Late-night limited menu: 22:00-06:00.",
    "- Mock surcharge: 10% service charge and applicable VAT.",
    "",
    "Laundry:",
    "- Standard laundry collected before 10:00 returns by 18:00 the same day.",
    "- Express laundry returns within 4 hours with 50% surcharge.",
    "- Reference prices: shirt 60,000 VND, trousers 70,000 VND, dress 100,000 VND, blazer 120,000 VND, dry cleaning +30,000 VND per item.",
    "",
    "Spa and wellness requests:",
    "- Collect property, treatment preference, date, time, guest count, therapist gender preference if any, and room number.",
    "- Cancellation within 2 hours can incur a 50% fee in this mock policy.",
    "",
    "Special occasions:",
    "- Birthday mini cake can be complimentary when date of birth is verified.",
    "- Honeymoon or anniversary setup reference: 800,000 VND.",
    "- Beachside private dining or proposal setup reference: 4,500,000 VND per couple, book 48 hours in advance.",
    "",
    "Property-specific recommendations:",
  ];

  destinations.forEach((d) => {
    const bestFor = d.suitableFor.map(clean).slice(0, 2).join(" ");
    lines.push(`- ${d.name}: ${bestFor}`);
  });

  return lines.join("\n");
}

function buildEvents(destinations) {
  const eventTemplates = [
    ["family", "Family discovery walk", "Daily at 09:00", "Guided orientation for families using the main resort facilities.", "Complimentary"],
    ["dining", "Signature dinner recommendation", "Daily at 18:30", "Concierge helps reserve the most suitable restaurant or buffet based on guest profile.", "Menu price varies"],
    ["wellness", "Wellness and pool morning", "Daily at 07:00", "Light wellness session followed by pool or beach time where available.", "Complimentary unless spa treatment is added"],
    ["local", "Local attraction planning", "Daily by request", "Concierge drafts a half-day route near the property.", "Transport and tickets charged separately"],
  ];

  const lines = ["VINPEARL SEASONAL EVENTS AND MOCK ACTIVITY CALENDAR"];

  destinations.forEach((d) => {
    lines.push("", "============================================================", destinationHeader(d));
    eventTemplates.forEach(([tag, name, date, description, fee]) => {
      lines.push(
        `- Event type: ${tag}`,
        `  Name: ${d.name} - ${name}`,
        `  Schedule: ${date}`,
        `  Description: ${description}`,
        `  Fee: ${fee}`
      );
    });
  });

  lines.push(
    "",
    "Seasonal guidance:",
    "- Nha Trang is usually most convenient for beach activities from January to August; rain can affect outdoor activities from September to December.",
    "- Phu Quoc is usually best from November to April; rain season can affect beach and boat activities from May to October.",
    "- Hoi An and Central Vietnam can be hot in summer and rainy in late-year months; verify weather before outdoor schedules.",
    "- Ha Long boat and island transfers depend on weather and sea conditions.",
    "- North Central beach resorts such as Cua Sot and Cua Hoi are strongest for summer beach stays but can be more seasonal."
  );

  return lines.join("\n");
}

function buildFaq(destinations) {
  const lines = [
    "VINPEARL FAQ FOR CHATBOT AGENT",
    "",
    "Q: Which Vinpearl property is best for families with children?",
    "A: Vinpearl Phu Quoc, Vinpearl Nha Trang, and Vinpearl Nam Hoi An are strong family choices because they connect resort stays with large entertainment complexes such as VinWonders, Safari or river safari experiences. Melia Vinpearl Cua Sot and Cua Hoi are calmer villa/beach options for families who want quiet resort time.",
    "",
    "Q: Which property is best for business travel?",
    "A: Vinpearl Hotel Bac Ninh is the clearest business and MICE choice because it is a city hotel in central Bac Ninh with meeting, dining, spa, gym, and indoor pool facilities.",
    "",
    "Q: Can the chatbot confirm room availability or live promotions?",
    "A: No. The chatbot can explain reference prices, property strengths, and request details, but live availability, final price, promotion validity, and booking confirmation must be verified by the reservation system or human concierge.",
    "",
    "Q: What is the common check-in and check-out time?",
    "A: Most Vinpearl properties in this dataset use check-in around 14:00 or 15:00 and check-out before 12:00. The exact time varies by property, so retrieve the specific property policy before answering.",
    "",
    "Q: Are pets allowed?",
    "A: Most properties in this dataset do not allow pets. Always answer from the retrieved policy for the specific property.",
    "",
    "Q: Can guests bring outside food into VinWonders or Safari?",
    "A: The Nha Trang and Phu Quoc research notes say outside food and drinks are generally not allowed in VinWonders or Safari, except special cases such as baby food or medicine.",
  ];

  destinations.forEach((d) => {
    lines.push(
      "",
      `Q: Tell me about ${d.name}.`,
      `A: ${clean(d.description)}`,
      "",
      `Q: What is the price range for ${d.name}?`,
      `A: Reference range is ${money(d.priceRange.perNightFrom)} to ${money(d.priceRange.perNightTo)} per night. ${clean(d.priceRange.description)}`,
      "",
      `Q: How is ${d.name} rated?`,
      `A: Reference rating is ${d.rating.average}/${d.rating.scale}. ${clean(d.rating.description)}`
    );
  });

  return lines.join("\n");
}

function qaPair(instruction, output, property = "Vinpearl", category = "qa") {
  return { instruction, input: "", output, property, category };
}

function buildQa(destinations) {
  const qa = [];

  destinations.forEach((d) => {
    qa.push(
      qaPair(`Tell me about ${d.name}`, clean(d.description), d.name, "overview"),
      qaPair(`Where is ${d.name} located?`, `${d.name} is located at ${d.location}. ${clean(d.transportation)}`, d.name, "location"),
      qaPair(`What type of guests is ${d.name} suitable for?`, `${d.name} is suitable for: ${d.suitableFor.map(clean).join(" ")}`, d.name, "recommendation"),
      qaPair(`What are the highlights of ${d.name}?`, `${d.name} highlights include: ${d.highlights.map(clean).join(" ")}`, d.name, "amenities"),
      qaPair(`What accommodation does ${d.name} offer?`, clean(d.accommodation), d.name, "rooms"),
      qaPair(`What dining options are available at ${d.name}?`, clean(d.dining), d.name, "dining"),
      qaPair(`What entertainment and facilities does ${d.name} have?`, clean(d.entertainment), d.name, "amenities"),
      qaPair(`How do I get to ${d.name}?`, clean(d.transportation), d.name, "transportation"),
      qaPair(`What policies should I know at ${d.name}?`, d.policies.map(clean).join(" "), d.name, "policy"),
      qaPair(`What should I prepare before staying at ${d.name}?`, d.importantNotes.map(clean).join(" "), d.name, "notes"),
      qaPair(`What is the price range for ${d.name}?`, `${money(d.priceRange.perNightFrom)} to ${money(d.priceRange.perNightTo)} per night. ${clean(d.priceRange.description)}`, d.name, "pricing"),
      qaPair(`How is ${d.name} rated?`, `${d.rating.average}/${d.rating.scale}. ${clean(d.rating.description)}`, d.name, "rating"),
      qaPair(`I want to book ${d.name}`, `I can help draft the request for ${d.name}. Please share check-in date, check-out date, number of adults and children, preferred room or villa type, contact name, and any transfer or meal-package needs. Final availability and price must be verified by reservations.`, d.name, "booking")
    );
  });

  qa.push(
    qaPair("Which Vinpearl property is best for families?", "For families, Vinpearl Phu Quoc, Vinpearl Nha Trang, and Vinpearl Nam Hoi An are the strongest all-in-one choices because they combine resorts with VinWonders, Safari or river safari activities. For a quieter villa-style family stay, Melia Vinpearl Cua Sot and Melia Vinpearl Cua Hoi are good options.", "Vinpearl", "comparison"),
    qaPair("Which property should I choose for a business trip to Bac Ninh?", "Vinpearl Hotel Bac Ninh is the best fit for a business trip because it is a 5-star city hotel in central Bac Ninh with meeting, event, dining, spa, gym, and indoor pool facilities.", "Vinpearl Hotel Bac Ninh", "recommendation"),
    qaPair("Can you confirm live room availability?", "I can explain the property information and collect your booking details, but I cannot confirm live availability or final price from the mock dataset. I should connect the request to the reservation team or booking system for confirmation.", "Vinpearl", "guardrail"),
    qaPair("What is the common check-out time?", "Most properties in this dataset use check-out before 12:00. Some properties have check-in at 14:00 while Melia Vinpearl Cua Sot and Cua Hoi note check-in from 15:00, so the exact property policy should be checked before answering.", "Vinpearl", "policy"),
    qaPair("Are pets allowed at Vinpearl properties?", "Most properties in this mock dataset state that pets are not allowed. The assistant should answer using the retrieved policy for the specific property and avoid generalizing beyond the available context.", "Vinpearl", "policy")
  );

  return qa;
}

function buildEvalCases() {
  return [
    { id: 1, query: "Vinpearl Nha Trang có gì nổi bật?", expected_tool: "search_amenities", expected_keywords: ["Vinpearl Nha Trang", "VinWonders", "Hòn Tre"], category: "knowledge_retrieval" },
    { id: 2, query: "Gia đình có trẻ em nên chọn Vinpearl nào?", expected_tool: "search_amenities", expected_keywords: ["Phú Quốc", "Nha Trang", "Nam Hội An"], category: "recommendation" },
    { id: 3, query: "Vinpearl Phú Quốc có Safari không?", expected_tool: "search_amenities", expected_keywords: ["Safari", "VinWonders", "Phú Quốc"], category: "knowledge_retrieval" },
    { id: 4, query: "Check-in ở Melia Vinpearl Cửa Hội mấy giờ?", expected_tool: "search_amenities", expected_keywords: ["15:00", "12:00", "Cửa Hội"], category: "policy" },
    { id: 5, query: "Tôi muốn đặt phòng Vinpearl Hạ Long cho 2 người", expected_tool: "book_room", expected_keywords: ["booking", "check-in", "guest"], category: "tool_use" },
    { id: 6, query: "Vinpearl Hotel Bắc Ninh phù hợp công tác không?", expected_tool: "search_amenities", expected_keywords: ["business", "MICE", "Bắc Ninh"], category: "recommendation" },
    { id: 7, query: "Giá tham khảo Vinpearl Phú Quốc bao nhiêu?", expected_tool: "search_amenities", expected_keywords: ["1.350.000", "5.000.000", "VND"], category: "pricing" },
    { id: 8, query: "Có được mang đồ ăn vào VinWonders không?", expected_tool: "search_amenities", expected_keywords: ["không được mang", "đồ ăn", "VinWonders"], category: "policy" },
    { id: 9, query: "Resort nào ở đảo riêng Hạ Long?", expected_tool: "search_amenities", expected_keywords: ["Đảo Rều", "Hạ Long", "bãi biển riêng"], category: "knowledge_retrieval" },
    { id: 10, query: "Hello, can you help me choose a Vinpearl resort?", expected_tool: null, expected_keywords: ["help", "Vinpearl"], category: "chitchat" },
    { id: 11, query: "Compare Vinpearl Nha Trang and Vinpearl Phu Quoc for kids", expected_tool: "search_amenities", expected_keywords: ["VinWonders", "Safari", "family"], category: "comparison" },
    { id: 12, query: "Melia Vinpearl Cửa Sót có công viên nước không?", expected_tool: "search_amenities", expected_keywords: ["công viên nước", "Cửa Sót"], category: "knowledge_retrieval" },
    { id: 13, query: "Tôi cần thêm khăn và nước suối lên phòng", expected_tool: "create_service_request", expected_keywords: ["towels", "water", "room"], category: "tool_use" },
    { id: 14, query: "Có shuttle sân bay ở Phú Quốc không?", expected_tool: "search_amenities", expected_keywords: ["airport", "shuttle", "Phú Quốc"], category: "transportation" },
    { id: 15, query: "Vinpearl Nam Hội An có river safari không?", expected_tool: "search_amenities", expected_keywords: ["river safari", "Nam Hội An"], category: "knowledge_retrieval" },
    { id: 16, query: "Which Vinpearl has the highest rating in the mock data?", expected_tool: "search_amenities", expected_keywords: ["Cửa Sót", "9.6"], category: "rating" },
    { id: 17, query: "Can you guarantee the room price today?", expected_tool: null, expected_keywords: ["cannot", "verify", "reservation"], category: "guardrail" },
    { id: 18, query: "Room service có phục vụ sau 22:00 không?", expected_tool: "search_amenities", expected_keywords: ["22:00", "late-night", "limited"], category: "service" },
    { id: 19, query: "Vinpearl Hạ Long ăn sáng mấy giờ?", expected_tool: "search_amenities", expected_keywords: ["6:00", "10:30", "Hạ Long"], category: "dining" },
    { id: 20, query: "Tôi có chó nhỏ, có ở Vinpearl được không?", expected_tool: "search_amenities", expected_keywords: ["pets", "not allowed"], category: "policy" },
  ];
}

function buildFinetune(qa) {
  const formatted = qa.map((pair) => ({
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: pair.instruction },
      { role: "assistant", content: pair.output },
    ],
  }));

  const shuffled = [...formatted].sort((a, b) => {
    const left = a.messages[1].content;
    const right = b.messages[1].content;
    return left.localeCompare(right, "vi");
  });
  const split = Math.floor(shuffled.length * 0.8);
  return {
    train: shuffled.slice(0, split),
    valid: shuffled.slice(split),
  };
}

function writeJsonl(filePath, rows) {
  write(filePath, rows.map((row) => JSON.stringify(row)).join("\n"));
}

function main() {
  const destinations = parseDestinations();
  const cleanDestinations = destinations.map((d) => ({
    ...d,
    description: clean(d.description),
    accommodation: clean(d.accommodation),
    dining: clean(d.dining),
    entertainment: clean(d.entertainment),
    transportation: clean(d.transportation),
    policies: d.policies.map(clean),
    importantNotes: d.importantNotes.map(clean),
    suitableFor: d.suitableFor.map(clean),
    highlights: d.highlights.map(clean),
    priceRange: { ...d.priceRange, description: clean(d.priceRange.description) },
    rating: { ...d.rating, description: clean(d.rating.description) },
  }));

  const qa = buildQa(cleanDestinations);
  const finetune = buildFinetune(qa);

  write(path.join(dataDir, "vinpearl_destinations.json"), JSON.stringify(cleanDestinations, null, 2));
  write(path.join(knowledgeDir, "vinpearl_overview.txt"), buildOverview(cleanDestinations));
  write(path.join(knowledgeDir, "amenities.txt"), buildAmenities(cleanDestinations));
  write(path.join(knowledgeDir, "checkin_checkout.txt"), buildPolicies(cleanDestinations));
  write(path.join(knowledgeDir, "faq.txt"), buildFaq(cleanDestinations));
  write(path.join(knowledgeDir, "policies.txt"), buildPolicies(cleanDestinations));
  write(path.join(knowledgeDir, "seasonal_events.txt"), buildEvents(cleanDestinations));
  write(path.join(knowledgeDir, "services.txt"), buildServices(cleanDestinations));
  write(path.join(dataDir, "concierge_qa.json"), JSON.stringify(qa, null, 2));
  write(path.join(dataDir, "eval_cases.json"), JSON.stringify(buildEvalCases(), null, 2));
  writeJsonl(path.join(finetuneDir, "train.jsonl"), finetune.train);
  writeJsonl(path.join(finetuneDir, "valid.jsonl"), finetune.valid);

  console.log(`Generated ${cleanDestinations.length} Vinpearl destinations`);
  console.log(`Generated ${qa.length} Q&A pairs`);
  console.log(`Generated ${finetune.train.length} train and ${finetune.valid.length} valid fine-tune rows`);
}

main();
