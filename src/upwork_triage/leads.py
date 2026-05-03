from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from upwork_triage.normalize import normalize_job_payload

ALLOWED_LEAD_STATUSES = {
    "new",
    "face_reviewed",
    "rejected",
    "promote",
    "hydrated",
    "applied",
    "archived",
}


@dataclass(frozen=True, slots=True)
class PromoteLeadResult:
    lead_id: int
    job_key: str
    previous_status: str
    new_status: str


def upsert_raw_lead(
    conn: sqlite3.Connection,
    *,
    job_key: str,
    source: str,
    captured_at: str,
    created_at: str,
    updated_at: str,
    upwork_job_id: str | None = None,
    source_rank: int | None = None,
    source_query: str | None = None,
    source_url: str | None = None,
    raw_title: str | None = None,
    raw_description: str | None = None,
    raw_client_summary: str | None = None,
    raw_pay_text: str | None = None,
    raw_proposals_text: str | None = None,
    raw_payload_json: str | None = None,
    lead_status: str = "new",
) -> int:
    if lead_status not in ALLOWED_LEAD_STATUSES:
        raise ValueError(f"Invalid lead_status: {lead_status}")

    cursor = conn.execute(
        """
        INSERT INTO raw_leads (
            job_key, upwork_job_id, source, source_rank, source_query, source_url,
            captured_at, raw_title, raw_description, raw_client_summary,
            raw_pay_text, raw_proposals_text, raw_payload_json,
            lead_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_key, source) DO UPDATE SET
            upwork_job_id = excluded.upwork_job_id,
            source_rank = excluded.source_rank,
            source_query = excluded.source_query,
            source_url = excluded.source_url,
            captured_at = excluded.captured_at,
            raw_title = excluded.raw_title,
            raw_description = excluded.raw_description,
            raw_client_summary = excluded.raw_client_summary,
            raw_pay_text = excluded.raw_pay_text,
            raw_proposals_text = excluded.raw_proposals_text,
            raw_payload_json = excluded.raw_payload_json,
            updated_at = excluded.updated_at
        RETURNING id
        """,
        (
            job_key,
            upwork_job_id,
            source,
            source_rank,
            source_query,
            source_url,
            captured_at,
            raw_title,
            raw_description,
            raw_client_summary,
            raw_pay_text,
            raw_proposals_text,
            raw_payload_json,
            lead_status,
            created_at,
            updated_at,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Upsert failed to return id")
    return int(row[0])


def fetch_next_raw_lead(
    conn: sqlite3.Connection,
    *,
    status: str = "new",
    source: str | None = None,
) -> dict[str, Any] | None:
    if status not in ALLOWED_LEAD_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    query = """
        SELECT
            raw_leads.*,
            me.parse_status AS manual_scrape_import_status,
            me.raw_manual_text AS manual_scrape_raw_manual_text,
            mp.parse_status AS manual_scrape_parse_status,
            mp.manual_title AS manual_scrape_manual_title,
            mp.manual_title_match_status AS manual_scrape_manual_title_match_status,
            mp.manual_title_match_warning AS manual_scrape_manual_title_match_warning,
            mp.connects_required AS manual_scrape_connects_required,
            mp.manual_proposals AS manual_scrape_manual_proposals,
            mp.manual_last_viewed_by_client AS manual_scrape_manual_last_viewed_by_client,
            mp.manual_hires_on_job AS manual_scrape_manual_hires_on_job,
            mp.manual_interviewing AS manual_scrape_manual_interviewing,
            mp.manual_invites_sent AS manual_scrape_manual_invites_sent,
            mp.manual_unanswered_invites AS manual_scrape_manual_unanswered_invites,
            mp.bid_high AS manual_scrape_bid_high,
            mp.bid_avg AS manual_scrape_bid_avg,
            mp.bid_low AS manual_scrape_bid_low,
            mp.client_payment_verified AS manual_scrape_client_payment_verified,
            mp.client_phone_verified AS manual_scrape_client_phone_verified,
            mp.client_rating AS manual_scrape_client_rating,
            mp.client_reviews_count AS manual_scrape_client_reviews_count,
            mp.client_country_normalized AS manual_scrape_client_country_normalized,
            mp.client_country_raw AS manual_scrape_client_country_raw,
            mp.client_location_text AS manual_scrape_client_location_text,
            mp.client_jobs_posted AS manual_scrape_client_jobs_posted,
            mp.client_hire_rate AS manual_scrape_client_hire_rate,
            mp.client_open_jobs AS manual_scrape_client_open_jobs,
            mp.client_total_spent AS manual_scrape_client_total_spent,
            mp.client_hires_total AS manual_scrape_client_hires_total,
            mp.client_hires_active AS manual_scrape_client_hires_active,
            mp.client_avg_hourly_paid AS manual_scrape_client_avg_hourly_paid,
            mp.client_hours_hired AS manual_scrape_client_hours_hired,
            mp.client_member_since AS manual_scrape_client_member_since
        FROM raw_leads
        LEFT JOIN manual_job_enrichments AS me
            ON me.job_key = raw_leads.job_key AND me.is_latest = 1
        LEFT JOIN manual_job_enrichment_parses AS mp
            ON mp.manual_enrichment_id = me.id
        WHERE raw_leads.lead_status = ?
    """
    params: list[Any] = [status]

    if source is not None:
        query += " AND raw_leads.source = ?\n"
        params.append(source)

    query += """
        ORDER BY
            CASE WHEN raw_leads.source = 'best_matches_ui' THEN 0 ELSE 1 END ASC,
            CASE WHEN raw_leads.source = 'best_matches_ui' THEN COALESCE(raw_leads.source_rank, 999999) ELSE 999999 END ASC,
            raw_leads.captured_at DESC,
            raw_leads.id DESC
        LIMIT 1
    """

    cursor = conn.execute(query, params)
    row = cursor.fetchone()
    if row is None:
        return None
    column_names = [col[0] for col in cursor.description]
    return dict(zip(column_names, row, strict=True))


def promote_raw_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    promoted_at: str | None = None,
) -> PromoteLeadResult:
    """
    Mark a raw lead as promoted from 'new' to 'promote'.
    Raises ValueError if lead missing or not in 'new' status.
    """
    cursor = conn.execute(
        "SELECT job_key, lead_status FROM raw_leads WHERE id = ?", (lead_id,)
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Raw lead not found: {lead_id}")

    job_key, previous_status = row
    if previous_status != "new":
        raise ValueError(
            f"Lead {lead_id} is not promotable from status {previous_status}"
        )

    if promoted_at is None:
        promoted_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    with conn:
        conn.execute(
            "UPDATE raw_leads SET lead_status = 'promote', updated_at = ? WHERE id = ?",
            (promoted_at, lead_id),
        )

    return PromoteLeadResult(
        lead_id=lead_id,
        job_key=job_key,
        previous_status=previous_status,
        new_status="promote",
    )


def render_raw_lead_review(lead: dict[str, Any], description_chars: int = 1600) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"Lead id:     {lead.get('id')}")
    lines.append(f"Status:      {lead.get('lead_status')}")
    lines.append(f"Source:      {lead.get('source')}")
    rank = lead.get("source_rank")
    lines.append(f"Rank:        {rank if rank is not None else '—'}")
    lines.append(f"Captured:    {lead.get('captured_at')}")
    lines.append(f"Job key:     {lead.get('job_key')}")
    lines.append(f"URL:         {lead.get('source_url') or '—'}")
    lines.append(f"Title:       {lead.get('raw_title') or '—'}")
    lines.append(f"Pay:         {lead.get('raw_pay_text') or '—'}")
    lines.append(f"Proposals:   {lead.get('raw_proposals_text') or '—'}")
    lines.append(f"Client:      {lead.get('raw_client_summary') or '—'}")
    raw_desc = lead.get("raw_description") or ""
    if len(raw_desc) > description_chars:
        raw_desc = raw_desc[:description_chars] + " [...]"
    lines.append(f"Description: {raw_desc or '—'}")

    lines.append("-" * 30)
    source = lead.get("source")
    if source == "best_matches_ui":
        # Best matches layer (unchanged)
        lines.append("best_matches_layer")
        lines.append("-" * 30)
        source_lines = _format_source_payload_fields(lead)
        lines.extend(source_lines)
    else:
        # Marketplace search layer
        lines.append("marketplace_search_layer")
        lines.append("-" * 30)
        mp_lines = _format_marketplace_search_layer_fields(lead)
        lines.extend(mp_lines)

        # Public search layer
        lines.append("-" * 30)
        lines.append("public_search_layer")
        lines.append("-" * 30)
        pub_lines = _format_public_search_layer_fields(lead)
        lines.extend(pub_lines)

    # by_id layer (unchanged)
    lines.append("-" * 30)
    lines.append("by_id_layer")
    lines.append("-" * 30)
    exact_lines = _format_exact_hydration_fields(lead)
    lines.extend(exact_lines)

    # manual_scrape_layer (new)
    lines.append("-" * 30)
    lines.append("manual_scrape_layer")
    lines.append("-" * 30)
    manual_lines = _format_manual_scrape_layer_fields(lead)
    lines.extend(manual_lines)

    lines.append("=" * 60)
    lines.append(
        "Next step: inspect this lead manually and decide whether to code a new approved discard tag."
    )
    return "\n".join(lines)


_FACE_VALUE_LABELS = [
    "Posted:",
    "Connects:",
    "Contract:",
    "Budget:",
    "Hourly range:",
    "Tier:",
    "Duration:",
    "Skills:",
    "Qualifications:",
    "Proposals:",
    "Hires:",
    "Persons to hire:",
    "Interviewing:",
    "Invites sent:",
    "Client last viewed:",
    "Payment:",
    "Client spend:",
    "Hire rate:",
    "Total hires:",
    "Jobs posted:",
    "Jobs open:",
    "Avg hourly paid:",
    "Hours hired:",
    "Member since:",
    "Market high/avg/low:",
    "Featured:",
]

_BEST_MATCHES_LAYER_LABELS = (
    "Posted:",
    "Contract:",
    "Budget:",
    "Tier:",
    "Duration:",
    "Skills:",
    "Proposals:",
    "Payment:",
    "Client country:",
    "Client spend:",
    "Featured:",)

_GRAPHQL_LAYER_LABELS = (
    "Posted:",
    "Contract:",
    "Budget:",
    "Hourly range:",
    "Skills:",
    "Proposals:",
    "Payment:",
    "Client country:",
    "Client spend:",
    "Total hires:",
    "Jobs posted:",)

_MARKETPLACE_SEARCH_LAYER_LABELS = (
    "Layer status:",
    "Source terms:",
    "Source surfaces:",
    "Job id:",
    "Ciphertext:",
    "Title:",
    "Posted:",
    "Skills:",
    "Payment:",
    "Client country:",
    "Client city:",
    "Client timezone:",
    "Client spend:",
    "Total hires:",
    "Jobs posted:",
    "Client reviews:",
    "Client feedback:",
    "Last contract title:",
    "Financial privacy:",
)

_PUBLIC_SEARCH_LAYER_LABELS = (
    "Layer status:",
    "Source terms:",
    "Source surfaces:",
    "Job id:",
    "Ciphertext:",
    "Title:",
    "Posted:",
    "Contract:",
    "Budget:",
    "Hourly range:",
    "Hourly budget type:",
    "Weekly budget:",
    "Tier:",
    "Duration:",
    "Engagement:",
    "Job status:",
    "Recno:",
    "Proposals:",
)

_BY_ID_LAYER_LABELS = (
    "Hydration status:",
    "Hydration error:",
    "Contract:",
    "Hourly range:",
    "Budget:",
    "Max budget:",
    "Experience level:",
    "Engagement type:",
    "Project duration unsure:",
    "Hires:",
    "Persons to hire:",
    "Invites sent:",
    "Invited to interview:",
    "Unanswered invites:",
    "Offers sent:",
    "Recommended:",
    "Client last activity:",
    "Payment:",
    "Client country:",
    "Client city:",
    "Client timezone:",
    "Cover letter required:",
    "Milestones allowed:",
    "Contractor type:",
    "English proficiency:",
    "Portfolio required:",
    "Hours worked required:",
    "Rising talent required:",
    "JSS required:",
    "Min earning required:",
    "Local check required:",
    "Local market:",
    "Location preference unsure:",
    "Location description:",
    "Location flexibility:",
)

_MANUAL_SCRAPE_LAYER_LABELS = (
    "Manual status:",
    "Manual title:",
    "Title match:",
    "Title warning:",
    "Connects:",
    "Proposals:",
    "Last viewed:",
    "Hires:",
    "Interviewing:",
    "Invites sent:",
    "Unanswered invites:",
    "Bid high/avg/low:",
    "Payment verified:",
    "Phone verified:",
    "Client rating:",
    "Client reviews:",
    "Client country:",
    "Client location:",
    "Jobs posted:",
    "Hire rate:",
    "Open jobs:",
    "Client spend:",
    "Total hires:",
    "Active hires:",
    "Avg hourly paid:",
    "Hours hired:",
    "Member since:",
    "Raw manual text:",
)


def _format_face_value_fields(lead: dict[str, Any]) -> list[str]:
    """Helper to format a universal list of face-value fields for any lead."""
    values = {label: "—" for label in _FACE_VALUE_LABELS}

    # 1. Always fill from raw_leads columns where available
    proposals_from_col = lead.get("raw_proposals_text")
    if proposals_from_col:
        values["Proposals:"] = _fmt_face_val(proposals_from_col)

    # 2. Extract from payload if available
    payload = _load_payload_dict(lead.get("raw_payload_json"))
    if payload:
        source = lead.get("source")
        if source == "best_matches_ui":
            _apply_best_matches_mapping(values, payload)
        else:
            norm = _try_normalize_payload_for_display(payload)
            if norm:
                _apply_normalized_mapping(values, norm)

        _apply_exact_marketplace_mapping(values, payload)

    # Build final lines
    lines: list[str] = []
    for label in _FACE_VALUE_LABELS:
        val = values[label]
        lines.append(f"{label:<20} {val}")
    return lines


def _load_payload_dict(raw_payload_json: str | None) -> dict[str, Any] | None:
    if not raw_payload_json:
        return None
    try:
        data = json.loads(raw_payload_json)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _try_normalize_payload_for_display(raw_payload: dict[str, Any]) -> Any | None:
    """
    Attempt to normalize a GraphQL-style payload for triage display.
    Display rendering must never crash review-next-lead; this is deliberately
    isolated to display fallback only and must not be reused for evaluator logic.
    """
    try:
        return normalize_job_payload(raw_payload).normalized
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def _fmt_face_val(val: Any) -> str:
    if val is None or val == "" or val == []:
        return "—"
    if isinstance(val, bool):
        return "yes" if val else "no"
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _format_manual_boolish(value: Any) -> str:
    """Format manual int/bool/string fields to yes/no/. for display."""
    if value is None:
        return "."
    # Handle boolean type first
    if isinstance(value, bool):
        return "yes" if value else "no"
    # Handle integer type
    if isinstance(value, int):
        if value == 1:
            return "yes"
        if value == 0:
            return "no"
        return "."  # Unknown integer value
    # Handle string type (case-insensitive, stripped)
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in ("1", "true", "yes"):
            return "yes"
        if stripped in ("0", "false", "no"):
            return "no"
        if stripped == "":
            return "."
        return "."  # Unknown string value
    # All other types (float, etc.) are unknown
    return "."


def _apply_best_matches_mapping(values: dict[str, str], data: dict[str, Any]) -> None:
    bm_mapping = {
        "posted-on": "Posted:",
        "job-type": "Contract:",
        "budget": "Budget:",
        "contractor-tier": "Tier:",
        "duration": "Duration:",
        "skills": "Skills:",
        "proposals": "Proposals:",
        "payment-verification-status": "Payment:",
        "client-country": "Client country:",
        "formatted-amount": "Client spend:",
        "is_featured": "Featured:",
    }
    for json_key, label in bm_mapping.items():
        if json_key in data:
            values[label] = _fmt_face_val(data[json_key])


def _apply_exact_marketplace_mapping(values: dict[str, str], data: dict[str, Any]) -> None:
    exact_raw = _get_nested_value(data, ("_exact_marketplace_raw",))
    if not isinstance(exact_raw, dict):
        return

    # Contract: contractTerms.contractType
    contract_type = _get_nested_value(exact_raw, ("contractTerms", "contractType"))
    if contract_type is not None:
        values["Contract:"] = _fmt_face_val(contract_type)

    # Hourly range: hourlyBudgetMin/hourlyBudgetMax
    hourly_terms = _get_nested_value(exact_raw, ("contractTerms", "hourlyContractTerms"))
    min_hourly = None
    max_hourly = None
    if isinstance(hourly_terms, dict):
        min_hourly = hourly_terms.get("hourlyBudgetMin")
        max_hourly = hourly_terms.get("hourlyBudgetMax")
    if min_hourly is not None or max_hourly is not None:
        hourly_range = _format_hourly_range(min_hourly, max_hourly)
        values["Hourly range:"] = hourly_range

    # Budget: fixedPriceContractTerms.amount (prefer displayValue, else rawValue formatted)
    amount = _get_nested_value(exact_raw, ("contractTerms", "fixedPriceContractTerms", "amount"))
    budget_val = None
    if isinstance(amount, dict):
        display_val = amount.get("displayValue")
        if display_val is not None and str(display_val).strip() != "":
            budget_val = str(display_val).strip()
        else:
            raw_val = amount.get("rawValue")
            if raw_val is not None:
                budget_val = _format_money(raw_val)
    if budget_val is not None:
        values["Budget:"] = budget_val

    # Max budget: fixedPriceContractTerms.maxAmount (prefer displayValue, else rawValue formatted)
    max_amount = _get_nested_value(exact_raw, ("contractTerms", "fixedPriceContractTerms", "maxAmount"))
    max_budget_val = None
    if isinstance(max_amount, dict):
        display_val = max_amount.get("displayValue")
        if display_val is not None and str(display_val).strip() != "":
            max_budget_val = str(display_val).strip()
        else:
            raw_val = max_amount.get("rawValue")
            if raw_val is not None:
                max_budget_val = _format_money(raw_val)
    if max_budget_val is not None:
        values["Max budget:"] = max_budget_val

    # Experience level: contractTerms.experienceLevel
    exp_level = _get_nested_value(exact_raw, ("contractTerms", "experienceLevel"))
    if exp_level is not None:
        values["Experience level:"] = _fmt_face_val(exp_level)

    # Engagement type: hourlyContractTerms.engagementType
    engagement = _get_nested_value(exact_raw, ("contractTerms", "hourlyContractTerms", "engagementType"))
    if engagement is not None:
        values["Engagement type:"] = _fmt_face_val(engagement)

    # Project duration unsure: hourlyContractTerms.notSureProjectDuration
    proj_unsure = _get_nested_value(exact_raw, ("contractTerms", "hourlyContractTerms", "notSureProjectDuration"))
    if proj_unsure is not None:
        values["Project duration unsure:"] = _fmt_face_val(proj_unsure)

    # Hires: activityStat.jobActivity.totalHired
    hires = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "totalHired"))
    if hires is not None:
        values["Hires:"] = _fmt_face_val(hires)

    # Persons to hire: contractTerms.personsToHire
    persons_to_hire = _get_nested_value(exact_raw, ("contractTerms", "personsToHire"))
    if persons_to_hire is not None:
        values["Persons to hire:"] = _fmt_face_val(persons_to_hire)

    # Invites sent: activityStat.jobActivity.invitesSent
    invites_sent = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "invitesSent"))
    if invites_sent is not None:
        values["Invites sent:"] = _fmt_face_val(invites_sent)

    # Invited to interview: activityStat.jobActivity.totalInvitedToInterview
    invited_interview = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "totalInvitedToInterview"))
    if invited_interview is not None:
        values["Invited to interview:"] = _fmt_face_val(invited_interview)

    # Unanswered invites: activityStat.jobActivity.totalUnansweredInvites
    unanswered = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "totalUnansweredInvites"))
    if unanswered is not None:
        values["Unanswered invites:"] = _fmt_face_val(unanswered)

    # Offers sent: activityStat.jobActivity.totalOffered
    offers = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "totalOffered"))
    if offers is not None:
        values["Offers sent:"] = _fmt_face_val(offers)

    # Recommended: activityStat.jobActivity.totalRecommended
    recommended = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "totalRecommended"))
    if recommended is not None:
        values["Recommended:"] = _fmt_face_val(recommended)

    # Client last activity: activityStat.jobActivity.lastClientActivity
    last_activity = _get_nested_value(exact_raw, ("activityStat", "jobActivity", "lastClientActivity"))
    if last_activity is not None:
        values["Client last activity:"] = _fmt_face_val(last_activity)

    # Payment: prefer paymentVerification.status, else paymentVerified
    payment_ver = _get_nested_value(exact_raw, ("clientCompanyPublic", "paymentVerification"))
    payment_val = None
    if isinstance(payment_ver, dict):
        status = payment_ver.get("status")
        if status is not None and str(status).strip() != "":
            payment_val = str(status).strip()
        else:
            payment_val = _fmt_face_val(payment_ver.get("paymentVerified"))
    if payment_val is not None:
        values["Payment:"] = payment_val

    # Client country: clientCompanyPublic.country.name
    country = _get_nested_value(exact_raw, ("clientCompanyPublic", "country"))
    if isinstance(country, dict):
        country_name = country.get("name")
        if country_name is not None:
            values["Client country:"] = _fmt_face_val(country_name)

    # Client city: clientCompanyPublic.city
    city = _get_nested_value(exact_raw, ("clientCompanyPublic", "city"))
    if city is not None:
        values["Client city:"] = _fmt_face_val(city)

    # Client timezone: clientCompanyPublic.timezone
    tz = _get_nested_value(exact_raw, ("clientCompanyPublic", "timezone"))
    if tz is not None:
        values["Client timezone:"] = _fmt_face_val(tz)

    # Cover letter required: contractorSelection.proposalRequirement.coverLetterRequired
    cover_letter = _get_nested_value(exact_raw, ("contractorSelection", "proposalRequirement", "coverLetterRequired"))
    if cover_letter is not None:
        values["Cover letter required:"] = _fmt_face_val(cover_letter)

    # Milestones allowed: contractorSelection.proposalRequirement.freelancerMilestonesAllowed
    milestones = _get_nested_value(exact_raw, ("contractorSelection", "proposalRequirement", "freelancerMilestonesAllowed"))
    if milestones is not None:
        values["Milestones allowed:"] = _fmt_face_val(milestones)

    # Contractor type: contractorSelection.qualification.contractorType
    contractor_type = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "contractorType"))
    if contractor_type is not None:
        values["Contractor type:"] = _fmt_face_val(contractor_type)

    # English proficiency: contractorSelection.qualification.englishProficiency
    english_prof = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "englishProficiency"))
    if english_prof is not None:
        values["English proficiency:"] = _fmt_face_val(english_prof)

    # Portfolio required: contractorSelection.qualification.hasPortfolio
    portfolio = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "hasPortfolio"))
    if portfolio is not None:
        values["Portfolio required:"] = _fmt_face_val(portfolio)

    # Hours worked required: contractorSelection.qualification.hoursWorked
    hours_worked = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "hoursWorked"))
    if hours_worked is not None:
        values["Hours worked required:"] = _fmt_face_val(hours_worked)

    # Rising talent required: contractorSelection.qualification.risingTalent
    rising_talent = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "risingTalent"))
    if rising_talent is not None:
        values["Rising talent required:"] = _fmt_face_val(rising_talent)

    # JSS required: contractorSelection.qualification.jobSuccessScore
    jss = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "jobSuccessScore"))
    if jss is not None:
        values["JSS required:"] = _fmt_face_val(jss)

    # Min earning required: contractorSelection.qualification.minEarning
    min_earning = _get_nested_value(exact_raw, ("contractorSelection", "qualification", "minEarning"))
    if min_earning is not None:
        values["Min earning required:"] = _fmt_face_val(min_earning)

    # Local check required: contractorSelection.location.localCheckRequired
    local_check = _get_nested_value(exact_raw, ("contractorSelection", "location", "localCheckRequired"))
    if local_check is not None:
        values["Local check required:"] = _fmt_face_val(local_check)

    # Local market: contractorSelection.location.localMarket
    local_market = _get_nested_value(exact_raw, ("contractorSelection", "location", "localMarket"))
    if local_market is not None:
        values["Local market:"] = _fmt_face_val(local_market)

    # Location preference unsure: contractorSelection.location.notSureLocationPreference
    loc_pref_unsure = _get_nested_value(exact_raw, ("contractorSelection", "location", "notSureLocationPreference"))
    if loc_pref_unsure is not None:
        values["Location preference unsure:"] = _fmt_face_val(loc_pref_unsure)

    # Location description: contractorSelection.location.localDescription
    loc_desc = _get_nested_value(exact_raw, ("contractorSelection", "location", "localDescription"))
    if loc_desc is not None:
        values["Location description:"] = _fmt_face_val(loc_desc)

    # Location flexibility: contractorSelection.location.localFlexibilityDescription
    loc_flex = _get_nested_value(exact_raw, ("contractorSelection", "location", "localFlexibilityDescription"))
    if loc_flex is not None:
        values["Location flexibility:"] = _fmt_face_val(loc_flex)


def _apply_normalized_mapping(values: dict[str, str], norm: Any) -> None:
    # Posted
    if norm.j_posted_at:
        values["Posted:"] = _fmt_face_val(norm.j_posted_at)
    elif norm.j_mins_since_posted is not None:
        values["Posted:"] = f"{norm.j_mins_since_posted} min ago"

    # Connects
    values["Connects:"] = _fmt_face_val(norm.j_apply_cost_connects)

    # Contract / Pay
    values["Contract:"] = _fmt_face_val(norm.j_contract_type)
    if norm.j_pay_fixed is not None:
        values["Budget:"] = _format_money(norm.j_pay_fixed)

    if norm.j_pay_hourly_low is not None or norm.j_pay_hourly_high is not None:
        values["Hourly range:"] = _format_hourly_range(
            norm.j_pay_hourly_low, norm.j_pay_hourly_high
        )

    # Skills / Qualifications
    values["Skills:"] = _fmt_face_val(norm.j_skills)
    values["Qualifications:"] = _fmt_face_val(norm.j_qualifications)

    # Activity
    values["Proposals:"] = _fmt_face_val(norm.a_proposals)
    values["Hires:"] = _fmt_face_val(norm.a_hires)
    values["Interviewing:"] = _fmt_face_val(norm.a_interviewing)
    values["Invites sent:"] = _fmt_face_val(norm.a_invites_sent)
    if norm.a_mins_since_cli_viewed is not None:
        values["Client last viewed:"] = f"{norm.a_mins_since_cli_viewed} min ago"

    # Client
    if norm.c_verified_payment == 1:
        values["Payment:"] = "Payment verified"
    elif norm.c_verified_payment == 0:
        values["Payment:"] = "Payment unverified"

    values["Client country:"] = _fmt_face_val(norm.c_country)
    values["Client spend:"] = _format_money(norm.c_hist_total_spent)
    values["Hire rate:"] = _fmt_face_val(norm.c_hist_hire_rate)
    values["Total hires:"] = _fmt_face_val(norm.c_hist_hires_total)
    values["Jobs posted:"] = _fmt_face_val(norm.c_hist_jobs_posted)
    values["Jobs open:"] = _fmt_face_val(norm.c_hist_jobs_open)
    values["Avg hourly paid:"] = _format_money(norm.c_hist_avg_hourly_rate)
    values["Hours hired:"] = _fmt_face_val(norm.c_hist_hours_hired)
    values["Member since:"] = _fmt_face_val(norm.c_hist_member_since)

    # Market
    if (
        norm.mkt_high is not None
        or norm.mkt_avg is not None
        or norm.mkt_low is not None
    ):
        values["Market high/avg/low:"] = (
            f"{_format_money(norm.mkt_high)} / "
            f"{_format_money(norm.mkt_avg)} / "
            f"{_format_money(norm.mkt_low)}"
        )


def _get_nested_value(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _format_money(value: Any) -> str:
    """Helper to format numeric money values safely."""
    if value is None:
        return "—"
    try:
        fval = float(value)
        # For simplicity, if it's a whole number show as int
        if fval.is_integer():
            return f"${int(fval)}"
        return f"${fval:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _format_hourly_range(low: Any, high: Any) -> str:
    """Helper to format hourly low/high range."""
    l = _format_money(low)
    h = _format_money(high)
    if l != "—" and h != "—":
        return f"{l}-{h}/hr"
    if l != "—":
        return f"{l}/hr"
    if h != "—":
        return f"{h}/hr"
    return "—"


def _format_source_payload_fields(lead: dict[str, Any]) -> list[str]:
    """Format face-value fields from the source payload only, excluding exact hydration data."""
    # Initialize with all universal labels to avoid KeyError in mapping functions
    values = {label: "—" for label in _FACE_VALUE_LABELS}

    # 1. Always fill from raw_leads columns where available
    proposals_from_col = lead.get("raw_proposals_text")
    if proposals_from_col:
        values["Proposals:"] = _fmt_face_val(proposals_from_col)

    # 2. Extract from payload if available
    payload = _load_payload_dict(lead.get("raw_payload_json"))
    if payload:
        source = lead.get("source")
        if source == "best_matches_ui":
            _apply_best_matches_mapping(values, payload)
        else:
            # Strip exact hydration keys to prevent contamination
            stripped_payload = {
                k: v for k, v in payload.items()
                if k not in ("_exact_marketplace_raw", "_exact_hydration_status", "_exact_hydration_error")
            }
            norm = _try_normalize_payload_for_display(stripped_payload)
            if norm:
                _apply_normalized_mapping(values, norm)

    # Determine supported labels for this lead's source
    source = lead.get("source")
    if source == "best_matches_ui":
        supported_labels = _BEST_MATCHES_LAYER_LABELS
    else:
        supported_labels = _GRAPHQL_LAYER_LABELS

    # Build final lines: only supported labels, convert "—" to "."
    lines: list[str] = []
    for label in supported_labels:
        val = values.get(label, "—")
        if val == "—":
            val = "."
        lines.append(f"{label:<20} {val}")
    return lines


def _format_exact_hydration_fields(lead: dict[str, Any]) -> list[str]:
    """Format face-value fields from exact marketplace hydration only."""
    # Initialize with all universal labels to avoid KeyError in mapping functions
    values = {label: "—" for label in _FACE_VALUE_LABELS}

    payload = _load_payload_dict(lead.get("raw_payload_json"))
    if payload is not None:
        # Populate hydration status/error from top-level payload keys
        status = payload.get("_exact_hydration_status")
        if status is not None:
            values["Hydration status:"] = _fmt_face_val(status)
        error = payload.get("_exact_hydration_error")
        if error is not None:
            values["Hydration error:"] = _fmt_face_val(error)
        # Apply exact marketplace mappings (uses _exact_marketplace_raw if present)
        _apply_exact_marketplace_mapping(values, payload)

    # Only render by_id layer supported labels, convert "—" to "."
    supported_labels = _BY_ID_LAYER_LABELS
    lines: list[str] = []
    for label in supported_labels:
        val = values.get(label, "—")
        if val == "—":
            val = "."
        lines.append(f"{label:<20} {val}")
    return lines


# ---------------------------------------------------------------------------
# New raw-path layer helpers for marketplace/public search layers
# ---------------------------------------------------------------------------

def _select_layer_payload(payload: dict[str, Any] | None, fragment_key: str) -> dict[str, Any] | None:
    """Return fragment dict if present and is a dict."""
    if not payload:
        return None
    fragment = payload.get(fragment_key)
    if isinstance(fragment, dict):
        return fragment
    return None


def _format_money_obj(value: Any) -> str:
    """Format money value that may be a dict with displayValue/rawValue."""
    if value is None:
        return "."
    if isinstance(value, dict):
        display = value.get("displayValue")
        if display is not None and str(display).strip() != "":
            return str(display).strip()
        raw = value.get("rawValue")
        if raw is not None:
            return _format_money(raw)
        return "."
    return _format_money(value)


def _format_skills(skills_val: Any) -> str:
    """Format skills list from marketplace raw (prettyName/name keys)."""
    if not isinstance(skills_val, list):
        return "."
    skill_names = []
    for skill in skills_val:
        if isinstance(skill, dict):
            name = skill.get("prettyName") or skill.get("name")
            if name:
                skill_names.append(str(name))
        elif isinstance(skill, str):
            skill_names.append(skill)
    return ", ".join(skill_names) if skill_names else "."


def _format_layer_rows(labels: tuple[str, ...], values: dict[str, str]) -> list[str]:
    """Generate formatted lines for a layer with . for missing supported labels."""
    lines = []
    for label in labels:
        val = values.get(label, ".")
        lines.append(f"{label:<20} {val}")
    return lines


def _format_marketplace_search_layer_fields(lead: dict[str, Any]) -> list[str]:
    """Format raw marketplace search layer fields from _marketplace_raw."""
    values = {label: "." for label in _MARKETPLACE_SEARCH_LAYER_LABELS}
    payload = _load_payload_dict(lead.get("raw_payload_json"))

    # Source terms/surfaces are always top-level if present
    if payload:
        source_terms = payload.get("_source_terms")
        if source_terms is not None:
            values["Source terms:"] = _fmt_face_val(source_terms)
        source_surfaces = payload.get("_source_surfaces")
        if source_surfaces is not None:
            values["Source surfaces:"] = _fmt_face_val(source_surfaces)

    mp_raw = _select_layer_payload(payload, "_marketplace_raw")
    if mp_raw:
        values["Layer status:"] = "present"
        # Populate marketplace fields
        if mp_raw.get("id") is not None:
            values["Job id:"] = _fmt_face_val(mp_raw["id"])
        if mp_raw.get("ciphertext") is not None:
            values["Ciphertext:"] = _fmt_face_val(mp_raw["ciphertext"])
        if mp_raw.get("title") is not None:
            values["Title:"] = _fmt_face_val(mp_raw["title"])
        if mp_raw.get("createdDateTime") is not None:
            values["Posted:"] = _fmt_face_val(mp_raw["createdDateTime"])
        if mp_raw.get("skills") is not None:
            values["Skills:"] = _format_skills(mp_raw["skills"])

        # Client fields
        client = mp_raw.get("client")
        if isinstance(client, dict):
            if client.get("verificationStatus") is not None:
                values["Payment:"] = _fmt_face_val(client["verificationStatus"])
            location = client.get("location")
            if isinstance(location, dict):
                if location.get("country") is not None:
                    values["Client country:"] = _fmt_face_val(location["country"])
                if location.get("city") is not None:
                    values["Client city:"] = _fmt_face_val(location["city"])
                if location.get("timezone") is not None:
                    values["Client timezone:"] = _fmt_face_val(location["timezone"])
            if client.get("totalSpent") is not None:
                values["Client spend:"] = _format_money_obj(client["totalSpent"])
            if client.get("totalHires") is not None:
                values["Total hires:"] = _fmt_face_val(client["totalHires"])
            if client.get("totalPostedJobs") is not None:
                values["Jobs posted:"] = _fmt_face_val(client["totalPostedJobs"])
            if client.get("totalReviews") is not None:
                values["Client reviews:"] = _fmt_face_val(client["totalReviews"])
            if client.get("totalFeedback") is not None:
                values["Client feedback:"] = _fmt_face_val(client["totalFeedback"])
            if client.get("lastContractTitle") is not None:
                values["Last contract title:"] = _fmt_face_val(client["lastContractTitle"])
            if client.get("hasFinancialPrivacy") is not None:
                values["Financial privacy:"] = _fmt_face_val(client["hasFinancialPrivacy"])
    else:
        values["Layer status:"] = "missing"


    return _format_layer_rows(_MARKETPLACE_SEARCH_LAYER_LABELS, values)


def _format_public_search_layer_fields(lead: dict[str, Any]) -> list[str]:
    """Format raw public search layer fields from _public_raw."""
    values = {label: "." for label in _PUBLIC_SEARCH_LAYER_LABELS}
    payload = _load_payload_dict(lead.get("raw_payload_json"))

    # Source terms/surfaces are always top-level if present
    if payload:
        source_terms = payload.get("_source_terms")
        if source_terms is not None:
            values["Source terms:"] = _fmt_face_val(source_terms)
        source_surfaces = payload.get("_source_surfaces")
        if source_surfaces is not None:
            values["Source surfaces:"] = _fmt_face_val(source_surfaces)

    pub_raw = _select_layer_payload(payload, "_public_raw")
    if pub_raw:
        values["Layer status:"] = "present"
        # Populate public fields
        if pub_raw.get("id") is not None:
            values["Job id:"] = _fmt_face_val(pub_raw["id"])
        if pub_raw.get("ciphertext") is not None:
            values["Ciphertext:"] = _fmt_face_val(pub_raw["ciphertext"])
        if pub_raw.get("title") is not None:
            values["Title:"] = _fmt_face_val(pub_raw["title"])
        # Posted: prefer publishedDateTime, fallback createdDateTime
        posted = pub_raw.get("publishedDateTime") or pub_raw.get("createdDateTime")
        if posted is not None:
            values["Posted:"] = _fmt_face_val(posted)
        if pub_raw.get("type") is not None:
            values["Contract:"] = _fmt_face_val(pub_raw["type"])
        # Budget
        if pub_raw.get("amount") is not None:
            values["Budget:"] = _format_money_obj(pub_raw["amount"])
        # Hourly range
        hourly_min = pub_raw.get("hourlyBudgetMin")
        hourly_max = pub_raw.get("hourlyBudgetMax")
        if hourly_min is not None or hourly_max is not None:
            values["Hourly range:"] = _format_hourly_range(hourly_min, hourly_max)
        if pub_raw.get("hourlyBudgetType") is not None:
            values["Hourly budget type:"] = _fmt_face_val(pub_raw["hourlyBudgetType"])
        # Weekly budget
        if pub_raw.get("weeklyBudget") is not None:
            values["Weekly budget:"] = _format_money_obj(pub_raw["weeklyBudget"])
        if pub_raw.get("contractorTier") is not None:
            values["Tier:"] = _fmt_face_val(pub_raw["contractorTier"])
        # Duration: prefer durationLabel, fallback duration
        duration = pub_raw.get("durationLabel") or pub_raw.get("duration")
        if duration is not None:
            values["Duration:"] = _fmt_face_val(duration)
        if pub_raw.get("engagement") is not None:
            values["Engagement:"] = _fmt_face_val(pub_raw["engagement"])
        if pub_raw.get("jobStatus") is not None:
            values["Job status:"] = _fmt_face_val(pub_raw["jobStatus"])
        if pub_raw.get("recno") is not None:
            values["Recno:"] = _fmt_face_val(pub_raw["recno"])
        if pub_raw.get("totalApplicants") is not None:
            values["Proposals:"] = _fmt_face_val(pub_raw["totalApplicants"])
    else:
        values["Layer status:"] = "missing"

    return _format_layer_rows(_PUBLIC_SEARCH_LAYER_LABELS, values)


# ---------------------------------------------------------------------------
# New manual_scrape_layer helper
# ---------------------------------------------------------------------------

def _format_manual_scrape_layer_fields(lead: dict[str, Any]) -> list[str]:
    """Format manual scrape layer fields from aliased manual columns."""
    values = {label: "." for label in _MANUAL_SCRAPE_LAYER_LABELS}

    # Manual status: prefer parse_status, then import_status
    parse_status = lead.get("manual_scrape_parse_status")
    import_status = lead.get("manual_scrape_import_status")
    if parse_status is not None and str(parse_status).strip() != "":
        values["Manual status:"] = str(parse_status)
    elif import_status is not None and str(import_status).strip() != "":
        values["Manual status:"] = str(import_status)

    # Manual title
    manual_title = lead.get("manual_scrape_manual_title")
    if manual_title is not None:
        values["Manual title:"] = str(manual_title)

    # Title match
    title_match = lead.get("manual_scrape_manual_title_match_status")
    if title_match is not None:
        values["Title match:"] = str(title_match)

    # Title warning
    title_warning = lead.get("manual_scrape_manual_title_match_warning")
    if title_warning is not None:
        values["Title warning:"] = str(title_warning)

    # Connects
    connects = lead.get("manual_scrape_connects_required")
    if connects is not None:
        values["Connects:"] = _fmt_face_val(connects)

    # Proposals
    proposals = lead.get("manual_scrape_manual_proposals")
    if proposals is not None:
        values["Proposals:"] = _fmt_face_val(proposals)

    # Last viewed
    last_viewed = lead.get("manual_scrape_manual_last_viewed_by_client")
    if last_viewed is not None:
        values["Last viewed:"] = _fmt_face_val(last_viewed)

    # Hires
    hires = lead.get("manual_scrape_manual_hires_on_job")
    if hires is not None:
        values["Hires:"] = _fmt_face_val(hires)

    # Interviewing
    interviewing = lead.get("manual_scrape_manual_interviewing")
    if interviewing is not None:
        values["Interviewing:"] = _fmt_face_val(interviewing)

    # Invites sent
    invites_sent = lead.get("manual_scrape_manual_invites_sent")
    if invites_sent is not None:
        values["Invites sent:"] = _fmt_face_val(invites_sent)

    # Unanswered invites
    unanswered = lead.get("manual_scrape_manual_unanswered_invites")
    if unanswered is not None:
        values["Unanswered invites:"] = _fmt_face_val(unanswered)

    # Bid high/avg/low
    def fmt_bid(val: Any) -> str:
        if val is None:
            return "."
        return _format_money(val)

    bid_high = lead.get("manual_scrape_bid_high")
    bid_avg = lead.get("manual_scrape_bid_avg")
    bid_low = lead.get("manual_scrape_bid_low")
    values["Bid high/avg/low:"] = f"{fmt_bid(bid_high)}/{fmt_bid(bid_avg)}/{fmt_bid(bid_low)}"

    # Payment verified
    pay_ver = lead.get("manual_scrape_client_payment_verified")
    if pay_ver is not None:
        values["Payment verified:"] = _format_manual_boolish(pay_ver)

    # Phone verified
    phone_ver = lead.get("manual_scrape_client_phone_verified")
    if phone_ver is not None:
        values["Phone verified:"] = _format_manual_boolish(phone_ver)

    # Client rating
    rating = lead.get("manual_scrape_client_rating")
    if rating is not None:
        values["Client rating:"] = _fmt_face_val(rating)

    # Client reviews
    reviews = lead.get("manual_scrape_client_reviews_count")
    if reviews is not None:
        values["Client reviews:"] = _fmt_face_val(reviews)

    # Client country: prefer normalized, fallback raw
    country_norm = lead.get("manual_scrape_client_country_normalized")
    if country_norm is not None and str(country_norm).strip() != "":
        values["Client country:"] = str(country_norm)
    else:
        country_raw = lead.get("manual_scrape_client_country_raw")
        if country_raw is not None and str(country_raw).strip() != "":
            values["Client country:"] = str(country_raw)

    # Client location
    location = lead.get("manual_scrape_client_location_text")
    if location is not None:
        values["Client location:"] = str(location)

    # Jobs posted
    jobs_posted = lead.get("manual_scrape_client_jobs_posted")
    if jobs_posted is not None:
        values["Jobs posted:"] = _fmt_face_val(jobs_posted)

    # Hire rate
    hire_rate = lead.get("manual_scrape_client_hire_rate")
    if hire_rate is not None:
        values["Hire rate:"] = _fmt_face_val(hire_rate)

    # Open jobs
    open_jobs = lead.get("manual_scrape_client_open_jobs")
    if open_jobs is not None:
        values["Open jobs:"] = _fmt_face_val(open_jobs)

    # Client spend
    spend = lead.get("manual_scrape_client_total_spent")
    if spend is not None:
        values["Client spend:"] = _format_money(spend)

    # Total hires
    total_hires = lead.get("manual_scrape_client_hires_total")
    if total_hires is not None:
        values["Total hires:"] = _fmt_face_val(total_hires)

    # Active hires
    active_hires = lead.get("manual_scrape_client_hires_active")
    if active_hires is not None:
        values["Active hires:"] = _fmt_face_val(active_hires)

    # Avg hourly paid
    avg_hourly = lead.get("manual_scrape_client_avg_hourly_paid")
    if avg_hourly is not None:
        values["Avg hourly paid:"] = _format_money(avg_hourly)

    # Hours hired
    hours_hired = lead.get("manual_scrape_client_hours_hired")
    if hours_hired is not None:
        values["Hours hired:"] = _fmt_face_val(hours_hired)

    # Member since
    member_since = lead.get("manual_scrape_client_member_since")
    if member_since is not None:
        values["Member since:"] = str(member_since)

    # Raw manual text: truncate to 240 chars, replace newlines with " | "
    raw_text = lead.get("manual_scrape_raw_manual_text")
    if raw_text is not None:
        text = str(raw_text)
        text = text.replace("\n", " | ")
        if len(text) > 240:
            text = text[:240] + " [...]"
        values["Raw manual text:"] = text

    return _format_layer_rows(_MANUAL_SCRAPE_LAYER_LABELS, values)


def fetch_raw_lead_counts(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    cursor = conn.execute(
        """
        SELECT lead_status, source, COUNT(*) as cnt
        FROM raw_leads
        GROUP BY lead_status, source
        """
    )
    results: dict[str, dict[str, int]] = {"by_status": {}, "by_source": {}}
    for lead_status, source, count in cursor:
        results["by_status"][lead_status] = results["by_status"].get(lead_status, 0) + count
        results["by_source"][source] = results["by_source"].get(source, 0) + count
    return results


def fetch_raw_leads(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    status: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM raw_leads WHERE 1=1"
    params: list[Any] = []

    if status is not None:
        if status not in ALLOWED_LEAD_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        query += " AND lead_status = ?"
        params.append(status)
    if source is not None:
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    return [dict(zip(column_names, row, strict=True)) for row in rows]
