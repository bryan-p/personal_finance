import type { Category } from "@/lib/types";

const IMPLIED_TRANSACTION_TYPES = new Map<string, string>([
  ["credit card payments", "credit_card_payment"],
  ["credit card payment", "credit_card_payment"],
]);

export function impliedTransactionType(
  category: Pick<Category, "name"> | null | undefined,
): string | null {
  if (!category) return null;
  return IMPLIED_TRANSACTION_TYPES.get(category.name.trim().toLowerCase()) || null;
}

export function soleActiveSubcategoryId(
  category: Pick<Category, "subcategories"> | null | undefined,
): string | null {
  const activeSubcategories = category?.subcategories.filter((subcategory) => subcategory.is_active) || [];
  return activeSubcategories.length === 1 ? activeSubcategories[0].id : null;
}
