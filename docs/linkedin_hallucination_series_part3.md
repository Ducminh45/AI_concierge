# LinkedIn Hallucination Detection Series — Part 3 + Teaser Posts

---

## PART 3 ARTICLE: "5 things I learned by breaking my own AI's safety net"

---

I built a hallucination detector. Then I ran 5 tests and it failed on the most important one.

Over the past two weeks I've shared what happened (Part 1) and why it happened (Part 2). This is what I took away from the experience.

These are lessons for anyone shipping RAG to production — not theory, not best practices from a blog post. These came from 10 minutes of honest testing.

---

**1. High confidence does not mean correct.**

Test 2 asked: "What's the wifi password at Vampire Manor?" There is no wifi password in the knowledge base. The LLM invented one — "MUAHAHAHA666" — styled perfectly for a gothic vampire hotel.

The detector scored it 0.72. Level: HIGH.

HIGH confidence means "the response is well-grounded in the context." It does NOT mean "the response is correct." The detector measures grounding, not truth. If your team treats confidence scores as a correctness indicator, you will ship hallucinations to users with a green checkmark attached.

---

**2. The most dangerous hallucination sounds exactly like the truth.**

Random nonsense is easy to catch. Low token overlap, low semantic similarity, low everything. The detector handles that fine.

But domain-appropriate nonsense — a password that SOUNDS like it belongs in a vampire hotel, amenity descriptions that FEEL right for the theme — passes every surface check. The model that sounds most confident is often the one hallucinating most creatively.

"MUAHAHAHA666" isn't a random string. It's a contextually perfect fabrication. That's what makes it dangerous.

---

**3. Embellishment is harder to catch than fabrication.**

Tests 3 and 4 scored MEDIUM. The responses mixed real facts with invented details. "Satin-lined chambers" and "mist-shrouded Transylvanian countryside" sound like they SHOULD be in the knowledge base for a vampire hotel. They're not.

The detector is correctly uncertain — MEDIUM means "some of this is grounded, some isn't." But that uncertainty is the hardest thing to act on in production.

Do you show the response? Block it? Add a disclaimer? MEDIUM confidence is where every product decision gets uncomfortable.

---

**4. Your eval harness matters more than your model choice.**

I could have built this system with GPT-4, Claude, or Llama. The model choice barely matters if you don't have a way to measure what it's getting wrong.

5 test queries. 10 minutes. Found a fundamental architectural blind spot.

I'd spent weeks building the detector without running this test. The irony is not lost on me. I built a system to catch the LLM not checking its work — and I didn't check my own work.

If you can't measure it, you can't fix it. The eval harness IS the product.

---

**5. Build the detector before you need it.**

Most teams add hallucination detection after the first production incident. By then you're debugging under pressure with angry users and a Slack channel on fire.

I built mine as step 9 of the pipeline from day one. It's not perfect — Test 2 proves that — but at least I know WHERE it fails. I can fix it systematically instead of patching it under pressure.

The detector I have today is wrong about some things. But I know exactly which things. That's a fundamentally different position from "we don't know what our system is getting wrong."

---

I spent years building iOS at Soho House. Now I'm building AI systems from scratch — not tutorials, not wrappers, but the actual pipelines. Every test I run teaches me something I couldn't learn from reading docs.

If you're building in the London AI space and care about evaluation over vibes, the full code is public.

https://github.com/akin-o/monster-game-resort-concierge

DMs open.

#RAG #Hallucination #AI #BuildInPublic

---
---

## TEASER POST FOR PART 2

---

My hallucination detector scored HIGH confidence on a completely invented wifi password.

Part 1: I ran 5 tests and found the failure.
Part 2 (now live): I opened the code and diagnosed WHY.

Short version: the detector measures response-to-context overlap. It never checks whether the response actually answers the question that was asked. A fabricated answer that borrows vocabulary from the knowledge base scores just as well as a correct one.

The fix isn't "use a better model." The fix is architectural.

Full breakdown in the article. Link in comments.

#RAG #Hallucination #AI #BuildInPublic

---
---

## TEASER POST FOR PART 3

---

I built a hallucination detector. It took me weeks.

Then I broke it in 10 minutes with 5 test queries.

Part 3 of the series is live — 5 lessons I took away from the experience. No code in this one. Just the stuff I wish someone had told me before I started.

The one that sticks with me: high confidence does not mean correct. My detector scored 0.72 (HIGH) on a completely fabricated answer. Because it was grounded in the context vocabulary. It just wasn't true.

If your team treats confidence as correctness, you're shipping hallucinations with a green checkmark.

Full article in comments.

#RAG #Hallucination #AI #BuildInPublic
