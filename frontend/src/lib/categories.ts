import type { Category } from "@/lib/types";

export function soleActiveSubcategoryId(
  category: Pick<Category, "subcategories"> | null | undefined,
): string | null {
  const activeSubcategories = category?.subcategories.filter((subcategory) => subcategory.is_active) || [];
  return activeSubcategories.length === 1 ? activeSubcategories[0].id : null;
}
