"""Prototype for the meals 2.0 ingestion pipeline (see ../../SPEC.md).

Runs the two LLM steps against a real Tesco order email and a real week of
free-text meals, to validate quality before any schema or endpoint work:

  step 1: receipt email text -> structured grocery items
  step 2: grocery items + week of meals -> item->meal links and proposed
          per-meal ingredient lists, leaving unmatched items unlinked

Usage:
  GOOGLE_API_KEY=... python ingestion_prototype.py [path-to.eml]
  python ingestion_prototype.py --extract-only [path-to.eml]   # no LLM call
"""

import email
import email.policy
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

DEFAULT_EML = Path.home() / "Downloads" / "receipt.eml"

# The real plan for the week of the sample receipt (collected Mon 1 June 2026)
WEEK_PLAN = {
    "2026-06-01": "Caesar Salad",
    "2026-06-02": "Spaghetti Bolognese",
    "2026-06-03": "Sausage and sweet potato mash",
    "2026-06-04": "Chicken pesto pasta",
    "2026-06-05": "Mie Goreng",
}


# ── step 0: .eml -> text ──────────────────────────────────────────────

def extract_receipt_text(eml_path: Path) -> str:
    from bs4 import BeautifulSoup

    with open(eml_path, "rb") as f:
        message = email.message_from_binary_file(f, policy=email.policy.default)

    body = message.get_body(preferencelist=("html", "plain"))
    if body is None:
        raise ValueError("No body part found in email")

    content = body.get_content()
    if body.get_content_type() == "text/html":
        soup = BeautifulSoup(content, "lxml")
        for tag in soup(["style", "script", "head"]):
            tag.decompose()
        content = soup.get_text(separator="\n")

    content = re.sub(r"\n\s*\n+", "\n", content)
    content = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    return content


# ── step 1: receipt text -> grocery items ─────────────────────────────

class GroceryItem(BaseModel):
    raw_name: str = Field(description="Product name exactly as printed on the receipt")
    quantity: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    storage_group: Optional[str] = Field(
        default=None, description="The receipt's own grouping heading, e.g. Fridge, Cupboard, Freezer"
    )
    household: bool = Field(
        description="True for non-food household products (cleaning, paper goods, toiletries)"
    )
    substituted_from: Optional[str] = Field(
        default=None,
        description="If this item was a substitution, the originally ordered product name",
    )


class ParsedReceipt(BaseModel):
    order_reference: Optional[str] = None
    order_date: Optional[str] = Field(default=None, description="ISO date of delivery/collection")
    total: Optional[float] = None
    items: list[GroceryItem]


PARSE_RECEIPT_PROMPT = """\
You are parsing a UK supermarket online-order receipt email into structured data.

Rules:
- One item per receipt line, with quantity and prices as printed.
- The receipt groups items under storage headings (e.g. Fridge, Cupboard); record the heading.
- Items marked with a dagger (†) are typically non-food household products; combine that
  marker with your own judgement to set the household flag.
- The substitutions section lists an originally ordered product followed by what was
  actually delivered. Output ONE item for what was delivered, with substituted_from set
  to the original product. Do not output the undelivered original as an item.
- Loose produce often embeds the purchased weight in the name (e.g. "Carrots Loose 0.348KG");
  keep the name as printed.
- Do not invent items that are not on the receipt.

Receipt text:
{receipt_text}
"""


# ── step 2: items + meals -> links and proposed ingredients ───────────

class ProposedIngredient(BaseModel):
    name: str = Field(description="Generic ingredient name, e.g. 'carrot', not the branded product name")
    from_grocery_item: Optional[str] = Field(
        default=None,
        description="raw_name of the receipt item evidencing this ingredient, if any",
    )


class MealLink(BaseModel):
    date: str
    meal_name: str
    proposed_ingredients: list[ProposedIngredient]
    confidence: str = Field(description="high / medium / low for the linking overall")
    notes: Optional[str] = None


class UnlinkedItem(BaseModel):
    raw_name: str
    category: str = Field(
        description="Why it is not linked to a meal: 'household', 'lunch-or-snack', 'staple', or 'unknown'"
    )


class IngestionResult(BaseModel):
    meal_links: list[MealLink]
    unlinked_items: list[UnlinkedItem]


LINK_MEALS_PROMPT = """\
A household plans evening meals in free text and does one weekly supermarket shop.
Below are the week's planned meals and the grocery items actually bought that week.

Your job, for each meal: identify which grocery items were plausibly bought FOR that
meal, and propose the meal's ingredient list (generic ingredient names) using general
cooking knowledge, marking which receipt items evidence which ingredients.

Critical rules — this data is noisy and that is expected:
- Do NOT force items onto meals. The shop also covers lunches, snacks, breakfasts and
  household goods. An item that does not clearly belong to a meal goes in unlinked_items.
- A meal may have few or no matching items (eaten out, cooked from cupboard stock,
  ingredients bought elsewhere). That is fine — never invent evidence.
- An ingredient can be proposed without receipt evidence (from_grocery_item null) when
  it is clearly core to the dish (e.g. spaghetti for bolognese) — but keep such
  proposals to obvious essentials.
- One grocery item may serve multiple meals (e.g. a parmesan block).
- Categorise unlinked items: household (non-food), lunch-or-snack, staple (regularly
  repurchased basics like milk, eggs, bread), or unknown.

Planned meals:
{meals}

Grocery items bought:
{items}
"""


def build_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("Set GOOGLE_API_KEY (https://aistudio.google.com/apikey) and re-run.")
    return ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key, temperature=0)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    eml_path = Path(args[0]) if args else DEFAULT_EML
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    receipt_text = extract_receipt_text(eml_path)
    (out_dir / "receipt_text.txt").write_text(receipt_text)
    print(f"extracted {len(receipt_text)} chars of receipt text -> output/receipt_text.txt")

    if "--extract-only" in sys.argv:
        return

    llm = build_llm()

    print("step 1: parsing receipt…")
    receipt = llm.with_structured_output(ParsedReceipt).invoke(
        PARSE_RECEIPT_PROMPT.format(receipt_text=receipt_text)
    )
    (out_dir / "parsed_receipt.json").write_text(receipt.model_dump_json(indent=2))
    print(f"  {len(receipt.items)} items, total £{receipt.total} -> output/parsed_receipt.json")

    print("step 2: linking items to the week's meals…")
    meals_block = "\n".join(f"  {date}: {meal}" for date, meal in WEEK_PLAN.items())
    items_block = "\n".join(
        f"  {i.quantity}x {i.raw_name}"
        + (f" [{i.storage_group}]" if i.storage_group else "")
        + (" [household]" if i.household else "")
        for i in receipt.items
    )
    result = llm.with_structured_output(IngestionResult).invoke(
        LINK_MEALS_PROMPT.format(meals=meals_block, items=items_block)
    )
    (out_dir / "ingestion_result.json").write_text(result.model_dump_json(indent=2))

    print("\n── report ────────────────────────────────────────────")
    for link in result.meal_links:
        print(f"\n{link.date}  {link.meal_name}  [{link.confidence}]")
        for ing in link.proposed_ingredients:
            evidence = f"  <- {ing.from_grocery_item}" if ing.from_grocery_item else "  (no receipt evidence)"
            print(f"    {ing.name}{evidence}")
        if link.notes:
            print(f"    note: {link.notes}")
    print("\nunlinked:")
    for item in result.unlinked_items:
        print(f"  [{item.category:14}] {item.raw_name}")
    print("\nfull JSON in prototype/output/")


if __name__ == "__main__":
    main()
