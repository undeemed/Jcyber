# Penetration Test Report: swisschems.is

**Date:** 2026-09-22
**Target:** swisschems.is + *.swisschems.is
**Tester:** Jcyber (automated + manual)
**Status:** Complete

---

## Executive Summary

Penetration test of swisschems.is (WordPress/WooCommerce e-commerce site) and associated subdomains. The most critical finding is a **High-severity PII leak** via directory listing on `/wp-content/uploads/`, exposing payment receipts containing the business operator's full name, email addresses, physical addresses, phone number, partial credit card details, and hidden business relationships between SwissChems, sarmguide.com, and Pumping Iron Store Ltd.

Additional findings include a CORS misconfiguration on the WP REST API, missing security headers enabling clickjacking, a WAF bypass via custom User-Agent, unauthenticated payment webhook endpoints, and input validation failures on the wholesale API.

No critical/high CVEs were found exploitable. All known CVEs for installed software versions are patched. SameSite=Lax cookie defaults (WordPress standard since 5.2) mitigate cross-origin credential-based attacks.

---

## Scope & Infrastructure

### Subdomains Discovered (6)

| Host | Status | Stack | Protection |
|---|---|---|---|
| swisschems.is / www | 200 | WordPress 7.1.2, WooCommerce 11.1.1, PHP, MySQL | Cloudflare + Wordfence |
| ws.swisschems.is | 200 | FastAPI/Starlette, Nginx 1.18.0, Ubuntu, EC2 | fail2ban (no WAF) |
| partners.swisschems.is | 200 | GoAffPro SPA, Caddy, HTTP/3 | Caddy |
| payment.swisschems.is | 403 | Cloudflare challenge | Cloudflare |
| verify.swisschems.is | 403 | Cloudflare challenge | Cloudflare |
| old.swisschems.is | 503 | Cloudways (CNAME) | Cloudflare |

### Plugins Identified (14)

| Plugin | Version | Source |
|---|---|---|
| WooCommerce | 11.1.1 | Asset fingerprint |
| 4square-gateway | 0.9.88 | Asset fingerprint |
| ajax-search-for-woocommerce (FiboSearch) | 1.34.2 | Asset fingerprint |
| lootly-woocommerce | 1.47.1 | Asset fingerprint |
| omnisend-connect | 0.1.1 | Asset fingerprint |
| swiss-stock-notifier | 1.1.0 | Asset fingerprint |
| woo-discount-rules(-pro) | 2.6.18 | Asset fingerprint |
| woo-product-bundle-premium (WPC) | 8.6.7 | Asset fingerprint |
| woocommerce-side-cart-premium | 4.8.8 | Asset fingerprint |
| CheckoutWC | Unknown | REST namespace |
| Rank Math SEO PRO | Unknown | REST namespace |
| Wordfence | Unknown | REST namespace |
| ATUM Inventory | Unknown | REST namespace |
| Object Cache Pro | Unknown | REST namespace |

---

## Findings

### F-01: PII & Financial Data Leak via Directory Listing (HIGH)

**Endpoint:** `https://swisschems.is/wp-content/uploads/`

Directory listing is enabled on the WordPress uploads directory, exposing the full file tree. Among 4752+ files in `2026/06/` alone, two payment receipts contain real PII:

**Payment_909990.pdf (DigitalOcean receipt):**
- Name: Antonio
- Email: pumpingironstoreltd@gmail.com
- Address: 100 East Hillsboro Boulevard, Deerfield Beach, FL 33441
- Phone: +971585562303
- Card: Visa ending 1147
- Amount: $57.50

**mailchimp-receipt-MC24123185.pdf (Mailchimp receipt):**
- Name: Enes Kiymaz
- Email: ekmarketinglife@gmail.com
- Business: sarmguide
- Address: 54 main road east, Oakland Park, FL 33111
- Card: Visa ending 1147, expires 06/2029
- Plan: Mailchimp Standard, 2500 contacts, $134.20
- Tax ID: MOSS No. EU372008134

**Verification:** All data cross-references as genuine. Pumping Iron Store Ltd is registered at UK Companies House (#11200542). Enes Kiymaz is CEO of Enhanced Labs (LinkedIn). sarmguide.com publishes SwissChems comparisons. Same Visa card across both receipts links the entities.

**Business impact beyond PII:** Reveals hidden ownership network -- sarmguide.com (positioned as "unbiased" review site) is operated by the same entity as SwissChems, constituting undisclosed affiliate relationships.

**Remediation:** Disable directory listing in Nginx/Apache config. Remove or restrict access to sensitive PDF files. Audit all uploaded files for PII.

---

### F-02: Missing Security Headers on Main Site (MEDIUM)

**Affected:** swisschems.is (main site only; ws.swisschems.is has proper headers)

Missing headers:
- `X-Frame-Options` -- clickjacking possible
- `Content-Security-Policy` -- no script/resource restrictions
- `X-Content-Type-Options` -- MIME sniffing possible
- `Referrer-Policy` -- referrer leakage

Contrast: ws.swisschems.is correctly sets `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Strict-Transport-Security`.

**Remediation:** Add security headers via Cloudflare page rules or WordPress plugin.

---

### F-03: CORS Origin Reflection with Credentials (MEDIUM, mitigated)

**Endpoint:** All `/wp-json/*` endpoints

`Access-Control-Allow-Origin` reflects ANY origin (including `null`) with `Access-Control-Allow-Credentials: true`. CORS also allows headers: `Authorization, X-WP-Nonce, Content-Disposition, Content-MD5, Content-Type, Cart-Token, Nonce`.

**Mitigating factor:** WordPress auth cookies default to `SameSite=Lax` since WP 5.2. Under Lax policy, cookies are not sent for cross-origin XHR/fetch requests, preventing the CORS misconfiguration from being exploited for authenticated data theft.

**Risk:** If the site ever changes cookie policy to `SameSite=None` (common for headless WooCommerce, payment widgets, or SSO integrations), the following become immediately exploitable:
- Cross-origin reading of `wc/store/cart` (billing/shipping PII)
- Nonce extraction via `wc/store/batch` response body
- Cart manipulation (add/remove items, apply coupons)

Additional: JSONP is enabled on the WC Store API (`?_jsonp=callback`), providing a second exfiltration channel that would also become live if cookies change to SameSite=None.

**Remediation:** Restrict CORS to known origins. Disable JSONP support on WC Store API. Do not change cookie SameSite policy without addressing CORS first.

---

### F-04: WAF Bypass via Custom User-Agent (MEDIUM)

**Bypass:** `User-Agent: LSVP-Portfolio-Client/2.0`

Bypasses both Wordfence and Cloudflare protections, exposing:
- 927 WP REST API routes across 41 namespaces
- Full plugin and namespace enumeration
- Route structure including payment, admin, and analytics endpoints
- Wordfence nonce and admin URL via `/wordfence/v1/authenticate`

All admin endpoints are properly auth-gated (401), so the bypass enables reconnaissance but not direct data access.

**Remediation:** Review Wordfence and Cloudflare UA allowlists. Remove overly permissive UA bypass rules.

---

### F-05: Unauthenticated Payment Webhook Endpoints (MEDIUM)

**Endpoints:**
- `POST /wp-json/wpay-2d/v1/callback`
- `POST /wp-json/wpay-hpp/v1/callback`

Both accept arbitrary POST data without authentication and return `{"received": true}` for any payload, including fake payment data (`order_id=99999&status=completed`).

Sending JSON-formatted data triggered a 502 Bad Gateway, crashing the origin server and revealing the hosting provider (Cloudways/cloudwayssites.com).

**Impact:** Depends on whether server-side signature verification exists. If the webhook only checks for the presence of data without validating a cryptographic signature, an attacker could forge payment confirmations.

**Remediation:** Implement HMAC signature verification on all payment webhooks. Return 403 for requests without valid signatures.

---

### F-06: Input Validation Failure on ws.swisschems.is (LOW-MEDIUM)

**Endpoint:** `POST /api/wholesale/access`

Non-string JSON types (integer, boolean, array, object) cause `500 Internal Server Error`. SQL metacharacters and certain special strings cause `503` (Python worker death, Nginx returns upstream error). The server recovers via worker restart; sustained abuse triggers fail2ban IP block on HTTP ports (defense working correctly).

This is a robustness/availability issue -- missing input validation on the `code` parameter. Not confirmed as SQL injection, deserialization, or template injection (all non-string types crash identically regardless of payload).

**Remediation:** Add Pydantic input validation to the FastAPI endpoint. Validate `code` as `str` type before processing.

---

### F-07: SSH Exposed on ws.swisschems.is (LOW)

**Service:** OpenSSH 8.9p1 Ubuntu-3ubuntu0.17 on port 22
**Host:** EC2 instance 3.235.46.207 (ec2-3-235-46-207.compute-1.amazonaws.com)

Publickey-only authentication (no password brute force). Patched for regreSSHion (CVE-2024-6387; patch level .17 > .10).

**Remediation:** Restrict SSH access to VPN/bastion IPs via AWS Security Group.

---

### F-08: GoAffPro API Token Leak (LOW)

**Endpoints:**
- `GET /wp-json/goaffpro/public_token` returns `"EzmuSEgAypnh"`
- `GET /wp-json/goaffpro/config` returns token, plugin version (2.7.11), store name

Enables unauthorized interaction with the GoAffPro affiliate program API.

**Remediation:** Restrict the `public_token` endpoint to authenticated requests.

---

### F-09: Information Disclosure (INFO)

| Item | Detail |
|---|---|
| Hosting provider | Cloudways (revealed via 502 error page) |
| EC2 instance | 3.235.46.207, us-east-1 |
| WordPress | 7.1.2 (RSS feed generator tag) |
| WooCommerce | 11.1.1 |
| Wordfence nonce | Returned unauthenticated at `/wordfence/v1/authenticate` |
| Admin URL | `https://swisschems.is/wp-admin/` |
| MCP adapter | `/mcp/mcp-adapter-default-server` (POST/GET/DELETE, auth-gated) |
| Real-time inventory | `stock_availability.text` shows exact counts ("492 in stock") |
| Accessible files | `license.txt`, `readme.html`, `wp-cron.php` |
| Backup files | `backup.sql`, `database.sql` return 403 (exist but blocked) |

---

## CVE Research

| CVE | Component | Severity | Target Version | Status |
|---|---|---|---|---|
| CVE-2026-3589 | WooCommerce batch CSRF | High | 11.1.1 | **Patched** (fix: 10.5.3); batch route removed |
| CVE-2026-48883 | WPC Product Bundles auth bypass | Medium | 8.6.7 | **Patched** (fix: 8.5.4) |
| CVE-2025-14298 | FiboSearch XSS | Medium | 1.34.2 | **Patched** (fix: 1.34.0) |
| CVE-2026-27654 | Nginx DAV heap overflow | High | 1.18.0 | DAV module not enabled (405 on MOVE/COPY) |
| CVE-2026-32647 | Nginx mp4 buffer overflow | High | 1.18.0 | mp4 module not configured (no mp4 locations) |
| CVE-2024-6387 | OpenSSH regreSSHion | Critical | 8.9p1-.17 | **Patched** (.17 > .10) |
| CVE-2026-48710 | Starlette Host header poisoning | Medium | Unknown | Cannot verify (IP blocked) |
| CVE-2026-54282 | Starlette path validation | Low | Unknown | Cannot verify (IP blocked) |

**Nuclei scans:** 7034 + 4370 templates executed against both targets. 0 matches (ws.swisschems.is scan partially invalid due to i/o timeouts from volume).

---

## Disproven / Investigated & Cleared

- **Author enumeration:** False positive -- random nonexistent slugs return identical results
- **XML-RPC brute force:** Disabled by Wordfence ("XML-RPC services are disabled")
- **Pingback SSRF:** Inconclusive (faultCode=0, empty faultString)
- **partners.swisschems.is exposures:** SPA catch-all -- all paths serve identical 7389-byte index.html
- **Cart-token JWT theft:** `t_` prefix = anonymous visitor session, not authentication credential
- **SQL injection (ws):** Single-observation pg_sleep delay was contaminated by rate limiting; no proportional timing confirmed
- **SSTI/template injection (ws):** 503s correlated with rate limiting, not template evaluation
- **Persistent DoS (ws):** IP-level block by fail2ban, not service crash
- **Python deserialization (ws):** All non-string types crash identically; `__reduce__` key irrelevant
- **WebDAV on WordPress:** Catch-all serves homepage HTML for any HTTP method
- **Subdomain takeover (old):** Active CNAME to Cloudways with Cloudflare proxy
- **CORS/JSONP account takeover:** SameSite=Lax cookies (WP default) prevent cross-origin cookie delivery
- **Batch nonce extraction zero-day:** Nonce is for User-ID: 0 (anonymous); same-session only
- **Open redirect:** Not found
- **CRLF injection:** Not found
- **Host header injection:** Returns 403
- **PHP info/debug pages:** Not found
- **Directory traversal (ws):** All blocked (400/404)

---

## Tools Used

**HexStrike (via Jcyber):** subfinder, httpx, nmap, nuclei (ffuf handler broken, katana timed out)

**Manual:** curl-based probing of 927+ WP REST API routes, all 41 namespaces, wholesale API endpoints, payment callbacks, CORS/JSONP validation, SameSite verification, directory enumeration, PDF content extraction, OSINT cross-referencing, CVE research and version matching, SQLi/XSS/SSRF/SSTI/deserialization testing, HTTP method/header manipulation, protocol-level attacks (HTTP/2, chunked TE, request smuggling)

---

## Recommendations (Priority Order)

1. **Disable directory listing** and audit `/wp-content/uploads/` for sensitive files (payment receipts, internal documents)
2. **Add security headers** (X-Frame-Options, CSP, X-Content-Type-Options, Referrer-Policy) on main site
3. **Fix CORS policy** to allowlist specific origins instead of reflecting any origin
4. **Disable JSONP** on WC Store API endpoints
5. **Add signature verification** to payment webhook callbacks
6. **Review WAF rules** to close the User-Agent bypass
7. **Add Pydantic type validation** to ws.swisschems.is `/api/wholesale/access` endpoint
8. **Restrict SSH** on ws.swisschems.is to VPN/bastion IPs via Security Group
9. **Remove or restrict** GoAffPro public_token endpoint
10. **Monitor** SameSite cookie policy -- do not change to None without first fixing CORS

---

*Report generated by Jcyber pentest toolkit. All testing performed within authorized scope.*
