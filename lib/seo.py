"""Shared search metadata and crawlable URLs for the build and source preview."""
from dataclasses import dataclass
from html import escape
import json
from xml.etree.ElementTree import Element, SubElement, tostring

SEO_INCLUDE = "<!-- include:site-seo -->"
SITE_URL = "https://www.nxflo.com"


@dataclass(frozen=True)
class Page:
    title: str
    description: str
    navigation: str | None
    image: str = "images/engineering-collaboration.webp"
    service: str | None = None
    indexable: bool = True
    keywords: tuple[str, ...] = ()
    article: str | None = None
    article_pdf: str | None = None


PAGES = {
    "admin.html": Page("Admin | Nexusflow", "Private Nexusflow administration.", None, indexable=False),
    "index.html": Page(
        "Data Integration & Engineering in Vancouver | Nexusflow",
        "Vancouver-based Nexusflow connects business systems, databases and devices, turning data into reliable pipelines, useful reporting and automated workflows.",
        "index.html", "images/engineering-collaboration.webp",
    ),
    "about.html": Page(
        "About Nexusflow | Vancouver Data & Integration Team",
        "Meet Nexusflow, a small Vancouver, Canada team delivering practical data engineering, systems integration, reporting and project-based technical support.",
        None, "images/about-team-collaboration.webp",
    ),
    "articles.html": Page(
        "Data & Reporting Articles: Research and Playbooks | Nexusflow",
        "Explore Nexusflow research and practical ETL and dashboard playbooks. Preview charts and download free PDFs, including the featured Stale by Thursday report.",
        "articles.html", "images/articles/stale-by-thursday-cover.webp",
    ),
    "etl-dashboard-process-playbook.html": Page(
        "ETL and Dashboard Process Playbook: Free PDF | Nexusflow",
        "Build reliable ETL pipelines and trusted dashboards. Preview cash-runway and refresh-cost charts, then download the free 28-page process playbook and templates.",
        "articles.html", "images/articles/etl-dashboard-playbook-cover.webp",
        keywords=("ETL process", "dashboard development", "data pipelines", "data quality gates", "pipeline monitoring", "FP&A dashboard", "source mapping", "ETL playbook"),
        article="ETL and Dashboard Process Playbook",
        article_pdf="articles/Nexusflow_ETL_Dashboard_Process_Playbook.pdf",
    ),
    "services.html": Page(
        "Data Integration & IT Consulting Services | Nexusflow",
        "Explore Nexusflow's BMS integration, Entra ID, Databricks, ETL pipelines, Power BI reporting and project-based IT support from Vancouver, Canada.",
        "services.html", "images/engineering-workbench.webp",
    ),
    "what-can-we-help-you-with.html": Page(
        "What Can We Help You With? | Nexusflow",
        "Outsource small technical tasks to Nexusflow: Excel reports, Power BI fixes, data extraction, integrations, workflow automation and industrial equipment connections.",
        "services.html", "images/engineering-workbench.webp",
    ),
    "contact.html": Page(
        "Contact Nexusflow | Vancouver IT & Data Consulting",
        "Discuss your integration, data or reporting project with our Vancouver team. Email sales@nxflo.com or call +1 (604) 260-9218. Small projects welcome.",
        "contact.html", "images/contact-client-consultation.webp",
    ),
    "bms-data-integration.html": Page(
        "BMS Data Integration in Vancouver | Nexusflow",
        "Connect building management system data to useful reporting. Nexusflow integrates HVAC, energy and sensor data with pipelines, data platforms and Power BI.",
        "services.html", service="Building management system data integration",
    ),
    "vancouver-it-support.html": Page(
        "Project-Based IT Support in Vancouver | Nexusflow",
        "Focused IT support for Vancouver businesses and local IT teams: data integration, reporting, automation and technical delivery without a full-time hire.",
        "services.html", service="Project-based IT support in Vancouver",
    ),
    "entra-id-integration.html": Page(
        "Microsoft Entra ID Integration & SSO | Nexusflow",
        "Vancouver-based Microsoft Entra ID integration for business applications: single sign-on, app registrations and scoped Microsoft Graph API workflows.",
        "services.html", service="Microsoft Entra ID application integration",
    ),
    "databricks-consulting.html": Page(
        "Databricks Consulting & Data Engineering | Nexusflow",
        "Nexusflow helps move growing data workloads to Apache Spark and Databricks, with scalable transformations, scheduled pipelines and reporting-ready data.",
        "services.html", "images/engineering-workbench.webp", service="Databricks consulting and data engineering",
    ),
    "etl-data-pipelines.html": Page(
        "ETL & Data Pipeline Development | Nexusflow",
        "Custom ETL data pipelines to extract, transform and load database, API and file data. Vancouver-based Nexusflow builds scheduled transfers with validation.",
        "services.html", "images/engineering-workbench.webp", service="ETL and data pipeline development",
    ),
    "power-bi-consulting.html": Page(
        "Power BI Consulting & Reporting in Vancouver | Nexusflow",
        "Power BI dashboards, data models and reliable refresh pipelines. Nexusflow connects your business data to clear operational reporting from Vancouver, Canada.",
        "services.html", "images/engineering-workbench.webp", service="Power BI consulting and reporting",
    ),
    "tools.html": Page(
        "Free Online Tools | Nexusflow",
        "Free apps and utilities by Nexusflow. Combine PDFs and view CSV or Excel files directly in your browser, without sign-up or file uploads.",
        None,
    ),
    "pdf-combiner.html": Page(
        "PDF Merge — Combine JPG & PDF Files Online for Free | Nexusflow",
        "Combine JPG images and PDF files into one downloadable PDF. Choose numbered upload boxes, arrange your files and name your PDF. Files stay in your browser.",
        None,
    ),
    "csv-viewer.html": Page(
        "Free CSV & Excel Viewer Online | Nexusflow",
        "Open CSV and Excel files in your browser. Sort data, resize columns, select worksheets and explore large datasets for free. Your files stay on your device.",
        None,
    ),
    "thanks.html": Page("Thank You | Nexusflow", "Contact the Nexusflow team about your project.", None, indexable=False),
}


def canonical_url(page_name: str) -> str:
    return SITE_URL + ("/" if page_name == "index.html" else "/" + page_name)


def render_metadata(page_name: str) -> str:
    page = PAGES[page_name]
    url = canonical_url(page_name)
    organization_id = SITE_URL + "/#organization"
    website_id = SITE_URL + "/#website"
    graph = [
        {
            "@type": "Organization", "@id": organization_id,
            "name": "Nexusflow Inc.", "legalName": "Nexusflow Inc.", "url": SITE_URL + "/",
            "description": "Vancouver-based consulting, development and R&D for data integration, reporting, automation and technology projects.",
            "logo": {"@type": "ImageObject", "url": SITE_URL + "/images/nxflo_logo_prod.png", "width": 400, "height": 155},
            "email": "sales@nxflo.com", "telephone": "+16042609218",
            "address": {"@type": "PostalAddress", "addressLocality": "Vancouver", "addressRegion": "BC", "addressCountry": "CA"},
            "identifier": {"@type": "PropertyValue", "propertyID": "BC Incorporation Number", "value": "BC1535270"},
            "sameAs": ["https://www.linkedin.com/company/nexusflow-inc/"],
        },
        {"@type": "WebSite", "@id": website_id, "url": SITE_URL + "/", "name": "Nexusflow", "publisher": {"@id": organization_id}, "inLanguage": "en-CA"},
        {"@type": "WebPage", "@id": url + "#webpage", "url": url, "name": page.title, "description": page.description, "isPartOf": {"@id": website_id}, "about": {"@id": organization_id}, "inLanguage": "en-CA"},
    ]
    if page.service:
        graph[-1]["mainEntity"] = {"@id": url + "#service"}
        graph[-1]["breadcrumb"] = {"@id": url + "#breadcrumb"}
        graph.extend([
            {"@type": "Service", "@id": url + "#service", "name": page.service, "serviceType": page.service, "url": url, "description": page.description, "provider": {"@id": organization_id}},
            {"@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_URL + "/"},
                {"@type": "ListItem", "position": 2, "name": "Services", "item": canonical_url("services.html")},
                {"@type": "ListItem", "position": 3, "name": page.service, "item": url},
            ]},
        ])
    if page.article:
        graph[-1]["mainEntity"] = {"@id": url + "#article"}
        graph.append({
            "@type": "Article", "@id": url + "#article", "headline": page.article,
            "description": page.description, "url": url, "mainEntityOfPage": url,
            "image": SITE_URL + "/" + page.image,
            "author": {"@id": organization_id}, "publisher": {"@id": organization_id},
            "keywords": list(page.keywords), "inLanguage": "en-CA",
            "encoding": {"@type": "MediaObject", "encodingFormat": "application/pdf", "contentUrl": SITE_URL + "/" + page.article_pdf},
        })
    structured = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    robots = "index, follow, max-image-preview:large" if page.indexable else "noindex, follow"
    tags = [
        f"<title>{escape(page.title)}</title>",
        f'<meta name="description" content="{escape(page.description, quote=True)}">',
        f'<meta name="robots" content="{robots}">',
        f'<link rel="canonical" href="{url}">',
    ]
    if page.keywords:
        tags.append(f'<meta name="keywords" content="{escape(", ".join(page.keywords), quote=True)}">')
    image_alt = page.article or ("Stale by Thursday report cover" if page_name == "articles.html" else "Engineering professionals collaborating on systems and data")
    for name, value in {"og:type": "article" if page.article else "website", "og:site_name": "Nexusflow", "og:locale": "en_CA", "og:title": page.title, "og:description": page.description, "og:url": url, "og:image": SITE_URL + "/" + page.image, "og:image:alt": image_alt}.items():
        tags.append(f'<meta property="{name}" content="{escape(value, quote=True)}">')
    for name, value in {"twitter:card": "summary_large_image", "twitter:title": page.title, "twitter:description": page.description, "twitter:image": SITE_URL + "/" + page.image, "twitter:image:alt": image_alt}.items():
        tags.append(f'<meta name="{name}" content="{escape(value, quote=True)}">')
    tags.append(f'<script type="application/ld+json">{structured}</script>')
    return "\n    ".join(tags)


def crawl_assets() -> dict[str, str]:
    # No fabricated lastmod dates: add one only when an actual content change can
    # be tracked. Utility pages stay crawlable so their noindex can be read.
    sitemap = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for name, page in PAGES.items():
        if page.indexable:
            SubElement(SubElement(sitemap, "url"), "loc").text = canonical_url(name)
    return {
        "robots.txt": f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n",
        "sitemap.xml": '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(sitemap, encoding="unicode") + "\n",
    }
