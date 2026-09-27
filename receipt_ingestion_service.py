"""Receipt ingestion: receipt email text -> grocery items -> links to the
week's planned meals with proposed ingredient lists.

Prompts were validated against a real Tesco order email and week plan
(see prototype/ingestion_prototype.py and SPEC.md).

Models mirror meals-contracts.yaml with camelCase wire names; they are defined
locally until the meals_contract wheel is regenerated at the next release.
"""

import logging
import os
import datetime
from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from auth_utils import create_llm_with_token

logger = logging.getLogger(__name__)


# ── wire models (contract-aligned) ────────────────────────────────────

class GroceryItemDto(BaseModel):
    id: Optional[int] = None
    rawName: str = Field(description="Product name exactly as printed on the receipt")
    quantity: int = 1
    unitPrice: Optional[float] = None
    totalPrice: Optional[float] = None
    storageGroup: Optional[str] = Field(
        default=None, description="The receipt's own grouping heading, e.g. Fridge, Cupboard, Freezer"
    )
    household: bool = Field(
        default=False, description="Non-food household product (cleaning, paper goods, toiletries)"
    )
    substitutedFrom: Optional[str] = Field(
        default=None, description="Originally ordered product if this item was a substitution"
    )


class ParseReceiptEmailRequest(BaseModel):
    receiptText: str


class ParseReceiptEmailResponse(BaseModel):
    orderReference: Optional[str] = None
    orderDate: Optional[datetime.date] = None
    total: Optional[float] = None
    items: list[GroceryItemDto] = []


class PlannedMealRefDto(BaseModel):
    date: datetime.date
    name: str


class LinkWeekRequest(BaseModel):
    meals: list[PlannedMealRefDto]
    items: list[GroceryItemDto]


class ProposedIngredientDto(BaseModel):
    name: str = Field(description="Generic ingredient name, e.g. 'carrot', not the branded product name")
    fromGroceryItem: Optional[str] = Field(
        default=None, description="rawName of the receipt item evidencing this ingredient, if any"
    )


class AiMealLinkDto(BaseModel):
    date: Optional[datetime.date] = None
    mealName: str
    confidence: Optional[str] = Field(default=None, description="high / medium / low")
    notes: Optional[str] = None
    ingredients: list[ProposedIngredientDto] = []


class UnlinkedItemDto(BaseModel):
    rawName: str
    category: str = Field(description="household / lunch-or-snack / staple / unknown")


class LinkWeekResponse(BaseModel):
    mealLinks: list[AiMealLinkDto] = []
    unlinkedItems: list[UnlinkedItemDto] = []


# ── LLM-facing models: dates as plain strings for schema compatibility ─

class _LlmParsedReceipt(BaseModel):
    orderReference: Optional[str] = None
    orderDate: Optional[str] = Field(default=None, description="ISO date of delivery/collection, e.g. 2026-06-01")
    total: Optional[float] = None
    items: list[GroceryItemDto] = []


class _LlmMealLink(BaseModel):
    date: Optional[str] = Field(default=None, description="ISO date of the planned meal, copied from the input")
    mealName: str
    confidence: Optional[str] = None
    notes: Optional[str] = None
    ingredients: list[ProposedIngredientDto] = []


class _LlmLinkResult(BaseModel):
    mealLinks: list[_LlmMealLink] = []
    unlinkedItems: list[UnlinkedItemDto] = []


PARSE_RECEIPT_PROMPT = """\
You are parsing a UK supermarket online-order receipt email into structured data.

Rules:
- One item per receipt line, with quantity and prices as printed.
- The receipt groups items under storage headings (e.g. Fridge, Cupboard); record the heading.
- Items marked with a dagger (†) are typically non-food household products; combine that
  marker with your own judgement to set the household flag.
- The substitutions section lists an originally ordered product followed by what was
  actually delivered. Output ONE item for what was delivered, with substitutedFrom set
  to the original product. Do not output the undelivered original as an item.
- Loose produce often embeds the purchased weight in the name (e.g. "Carrots Loose 0.348KG");
  keep the name as printed.
- Do not invent items that are not on the receipt.

Receipt text:
{receipt_text}
"""

LINK_WEEK_PROMPT = """\
A household plans evening meals in free text and does one weekly supermarket shop.
Below are the week's planned meals and the grocery items actually bought that week.

Your job, for each meal: identify which grocery items were plausibly bought FOR that
meal, and propose the meal's ingredient list (generic ingredient names) using general
cooking knowledge, marking which receipt items evidence which ingredients.

Critical rules — this data is noisy and that is expected:
- Do NOT force items onto meals. The shop also covers lunches, snacks, breakfasts and
  household goods. An item that does not clearly belong to a meal goes in unlinkedItems.
- A meal may have few or no matching items (eaten out, cooked from cupboard stock,
  ingredients bought elsewhere). That is fine — never invent evidence.
- An ingredient can be proposed without receipt evidence (fromGroceryItem null) when
  it is clearly core to the dish (e.g. spaghetti for bolognese) — but keep such
  proposals to obvious essentials.
- One grocery item may serve multiple meals (e.g. a parmesan block).
- Categorise unlinked items: household (non-food), lunch-or-snack, staple (regularly
  repurchased basics like milk, eggs, bread), or unknown.
- When referencing an item (fromGroceryItem, rawName) use its exact name as given
  inside the quotes — never include the quantity or storage annotations.

Planned meals:
{meals}

Grocery items bought:
{items}
"""


class ReceiptIngestionService:

    def parse_receipt(self, request: ParseReceiptEmailRequest, access_token: Optional[str]) -> ParseReceiptEmailResponse:
        llm = self._llm(access_token)
        parsed: _LlmParsedReceipt = llm.with_structured_output(_LlmParsedReceipt).invoke(
            PARSE_RECEIPT_PROMPT.format(receipt_text=request.receiptText)
        )
        logger.info(f"Parsed receipt: {len(parsed.items)} items, total {parsed.total}")
        return ParseReceiptEmailResponse(
            orderReference=parsed.orderReference,
            orderDate=_to_date(parsed.orderDate),
            total=parsed.total,
            items=parsed.items,
        )

    def link_week(self, request: LinkWeekRequest, access_token: Optional[str]) -> LinkWeekResponse:
        llm = self._llm(access_token)
        meals_block = "\n".join(f"  {meal.date.isoformat()}: {meal.name}" for meal in request.meals)
        items_block = "\n".join(
            f'  - "{item.rawName}"'
            + f" (x{item.quantity}"
            + (f", {item.storageGroup}" if item.storageGroup else "")
            + (", household" if item.household else "")
            + ")"
            for item in request.items
        )
        result: _LlmLinkResult = llm.with_structured_output(_LlmLinkResult).invoke(
            LINK_WEEK_PROMPT.format(meals=meals_block, items=items_block)
        )
        logger.info(f"Linked {len(result.mealLinks)} meals, {len(result.unlinkedItems)} unlinked items")
        return LinkWeekResponse(
            mealLinks=[
                AiMealLinkDto(
                    date=_to_date(link.date),
                    mealName=link.mealName,
                    confidence=link.confidence,
                    notes=link.notes,
                    ingredients=link.ingredients,
                )
                for link in result.mealLinks
            ],
            unlinkedItems=result.unlinkedItems,
        )

    def _llm(self, access_token: Optional[str]) -> ChatGoogleGenerativeAI:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            logger.info("Using GOOGLE_API_KEY for ingestion LLM (dev override)")
            return ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key, temperature=0)
        return create_llm_with_token(access_token=access_token, temperature=0)


def _to_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value.strip()[:10])
    except ValueError:
        logger.warning(f"LLM returned unparseable date: {value}")
        return None
