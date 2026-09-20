export function returnToSource(router, route, fallback) {
  const redirect = String(route.query.redirect || "");
  if (redirect.startsWith("/") && !redirect.startsWith("//")) return router.push(redirect);
  return router.push(fallback);
}
