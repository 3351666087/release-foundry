import { notFound } from "next/navigation";

import { ProductApp } from "@/components/product-app";
import { generatedRoutes, isProductRoute } from "@/lib/routes";

export const dynamicParams = false;

export function generateStaticParams() {
  return generatedRoutes.map((section) => ({ section }));
}

export default async function ProductSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!isProductRoute(section)) notFound();
  return <ProductApp route={section} />;
}
