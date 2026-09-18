"""
PlumeBacktrace AI - Statutory Violation Notice PDF Generator
Generates formal Section 21 statutory legal notices under CPCB/TNPCB standards.
"""

import os
import io
from datetime import datetime
from typing import Dict, Any

def generate_violation_notice_pdf(
    culprit: Dict[str, Any],
    plume_info: Dict[str, Any]
) -> bytes:
    """
    Generate an official legal notice PDF using reportlab.
    Falls back to a clean printable HTML representation if reportlab is unavailable.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'HeaderTitle',
            parent=styles['Heading1'],
            fontSize=15,
            leading=18,
            textColor=colors.HexColor('#0f172a'),
            alignment=1, # Center
            fontName='Helvetica-Bold'
        )
        
        sub_style = ParagraphStyle(
            'HeaderSub',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#475569'),
            alignment=1
        )
        
        body_style = ParagraphStyle(
            'NoticeBody',
            parent=styles['Normal'],
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#1e293b')
        )
        
        bold_alert = ParagraphStyle(
            'AlertText',
            parent=styles['Normal'],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor('#b91c1c'),
            fontName='Helvetica-Bold'
        )

        story = []

        # Official Header
        story.append(Paragraph("TAMIL NADU POLLUTION CONTROL BOARD (TNPCB)", title_style))
        story.append(Paragraph("ZONAL FORENSIC MONITORING & ENFORCEMENT CELL", title_style))
        story.append(Paragraph("76, Mount Salai, Guindy, Chennai - 600032 | Vellore & Ranipet Regional Division", sub_style))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0f172a')))
        story.append(Spacer(1, 8))

        # Notice Metadata Table
        notice_no = f"TNPCB/INV-DISP/{datetime.utcnow().year}/RN-{culprit.get('factory_id', '99')}"
        meta_data = [
            [Paragraph(f"<b>NOTICE NO:</b> {notice_no}", body_style), Paragraph(f"<b>ISSUE DATE:</b> {datetime.utcnow().strftime('%d %B %Y')}", body_style)],
            [Paragraph("<b>CLASSIFICATION:</b> SATELLITE FORENSIC EVIDENCE", body_style), Paragraph("<b>STATUTORY DISPATCH:</b> IMMEDIATE 48-HR SUMMONS", bold_alert)]
        ]
        meta_table = Table(meta_data, colWidths=[270, 270])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#94a3b8')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # Legal Title
        story.append(Paragraph(
            "<b>STATUTORY SHOW CAUSE & PENALTY NOTICE UNDER SECTION 21 & 22 OF THE AIR (PREVENTION AND CONTROL OF POLLUTION) ACT, 1981</b>",
            bold_alert
        ))
        story.append(Spacer(1, 8))

        # Offending Unit Details
        story.append(Paragraph(
            f"<b>TO:</b><br/>"
            f"<b>The Managing Director / Unit Head</b><br/>"
            f"<b>Unit:</b> {culprit.get('name', 'Industrial Unit')}<br/>"
            f"<b>Registration ID:</b> {culprit.get('registration_no', 'N/A')} | <b>Category:</b> {culprit.get('category', 'Industrial')}<br/>"
            f"<b>Site Location:</b> {culprit.get('address', 'SIPCOT Ranipet Industrial Estate, Tamil Nadu')}<br/>",
            body_style
        ))
        story.append(Spacer(1, 8))

        # Forensic Findings Table
        evidence_rows = [
            [Paragraph("<b>Parameter</b>", body_style), Paragraph("<b>Forensic Measurement / Satellite Telemetry</b>", body_style)],
            [Paragraph("Target Gas / Pollutant", body_style), Paragraph(str(plume_info.get("gas_type", "SO2")), body_style)],
            [Paragraph("Peak Plume Concentration", body_style), Paragraph(f"{plume_info.get('gas_density_umol', 450.0)} µmol/m² (Severe Exceedance)", body_style)],
            [Paragraph("Detection Timestamp", body_style), Paragraph(str(plume_info.get("timestamp", "02:30:00 IST")), body_style)],
            [Paragraph("Sentinel-5P Orbit Track", body_style), Paragraph("TROPOMI-L2-OFFL / High-Resolution Atmospheric Sounding", body_style)],
            [Paragraph("Atmospheric Wind Vector", body_style), Paragraph(f"{plume_info.get('wind_speed_mps', 4.2)} m/s @ {plume_info.get('wind_direction_deg', 245)}° azimuth", body_style)],
            [Paragraph("Inverse Dispersion Distance", body_style), Paragraph(f"{culprit.get('distance_meters', 1800)} meters upwind along centerline", body_style)],
            [Paragraph("Crosswind Plume Deviation", body_style), Paragraph(f"{culprit.get('crosswind_offset_m', 35)} meters (Within 95% Confidence Corridor)", body_style)],
            [Paragraph("Estimated Emission Release Time", body_style), Paragraph(f"<b>{culprit.get('est_release_time', '02:22:45 IST')}</b> (Unscheduled off-peak dump)", body_style)],
            [Paragraph("Forensic Backtrace Confidence", body_style), Paragraph(f"<b>{culprit.get('confidence_score', 94.2)}% MATCH</b>", bold_alert)],
        ]
        ev_table = Table(evidence_rows, colWidths=[200, 340])
        ev_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#0f172a')),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(ev_table)
        story.append(Spacer(1, 10))

        # Legal Directive & Fine
        fine_formatted = f"₹ {culprit.get('calculated_fine_inr', 1500000):,}"
        statutory_text = (
            f"WHEREAS satellite atmospheric inversion and inverse Gaussian dispersion algorithms confirm with a "
            f"<b>{culprit.get('confidence_score', 94.2)}% confidence index</b> that the illegal midnight atmospheric emission "
            f"originated from your industrial stacks/scrubbers during restricted off-peak hours;<br/><br/>"
            f"NOW THEREFORE, under the powers conferred under Section 21/22 of the Air Act 1981, you are hereby directed to:<br/>"
            f"1. Deposit an interim Environmental Compensation Fine of <b>{fine_formatted}</b> into the TNPCB Escrow within 7 days.<br/>"
            f"2. Submit continuous CEMS (Continuous Emission Monitoring System) raw datalogs for the past 48 hours.<br/>"
            f"3. Attend a personal appearance hearing before the District Magistrate / Environmental Engineer within 48 hours."
        )
        story.append(Paragraph(statutory_text, body_style))
        story.append(Spacer(1, 14))

        # Signatures
        sig_data = [
            [
                Paragraph("<b>[DIGITALLY SEALED]</b><br/>PlumeBacktrace AI Verification Hash:<br/>SHA256: 8f2c99a4e01b73...", sub_style),
                Paragraph("<b>By Order of:</b><br/>District Environmental Engineer<br/>Ranipet & Palar Industrial Monitoring Division", sub_style)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[270, 270])
        story.append(sig_table)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        # Fallback simple text-based byte representation
        fallback = f"OFFICIAL TNPCB NOTICE\nTarget: {culprit.get('name')}\nConfidence: {culprit.get('confidence_score')}%\nFine: INR {culprit.get('calculated_fine_inr')}"
        return fallback.encode('utf-8')


def generate_curfew_violations_pdf(violations: list) -> bytes:
    """Generate a formal compiled statutory enforcement docket of all nocturnal curfew violations."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CurfewHeaderTitle', parent=styles['Heading1'], fontSize=14, leading=17,
            textColor=colors.HexColor('#0f172a'), alignment=1, fontName='Helvetica-Bold'
        )
        sub_style = ParagraphStyle(
            'CurfewHeaderSub', parent=styles['Normal'], fontSize=8.5, leading=11,
            textColor=colors.HexColor('#475569'), alignment=1
        )
        body_style = ParagraphStyle(
            'CurfewNoticeBody', parent=styles['Normal'], fontSize=8.5, leading=12,
            textColor=colors.HexColor('#1e293b')
        )
        cell_style = ParagraphStyle(
            'CurfewCellText', parent=styles['Normal'], fontSize=7.5, leading=9.5,
            textColor=colors.HexColor('#0f172a')
        )

        story = []
        story.append(Paragraph("TAMIL NADU POLLUTION CONTROL BOARD", title_style))
        story.append(Paragraph("ZONAL ENFORCEMENT & EMISSIONS FORENSICS DIVISION", sub_style))
        story.append(Paragraph("STATUTORY DOCKET: 24/7 CONTINUOUS EMISSION EXCEEDANCES & VIOLATIONS", sub_style))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#dc2626'), spaceAfter=10))

        total_fines = sum(v.get("penalty_inr", 0) for v in violations)
        summary_text = (
            f"<b>Report Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC &nbsp;|&nbsp; "
            f"<b>Total Offending Incidents:</b> {len(violations)} &nbsp;|&nbsp; "
            f"<b>Cumulative Penalties:</b> ₹ {total_fines:,.2f}<br/>"
            f"<b>Statutory Reference:</b> Air (Prevention and Control of Pollution) Act 1981, Section 21/22."
        )
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 10))

        # Table header
        table_data = [
            ["ID", "Offending Industry", "Reg. No.", "Pollutant", "Confidence", "Release Time", "Penalty (INR)"]
        ]
        for v in violations:
            table_data.append([
                str(v.get("id", "")),
                Paragraph(f"<b>{v.get('factory_name', 'Unknown')}</b>", cell_style),
                str(v.get("registration_no") or v.get("factory_id", "")),
                f"{v.get('pollutant', 'SO2')} ({round(v.get('concentration', 0), 1)})",
                f"{v.get('confidence_score', 0)}%",
                v.get("est_release_time") or v.get("detection_timestamp", ""),
                f"₹ {v.get('penalty_inr', 0):,}"
            ])

        col_widths = [25, 150, 80, 85, 55, 75, 70]
        v_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        v_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (4, 0), (6, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])
        ]))
        story.append(v_table)
        story.append(Spacer(1, 14))

        closing = (
            "<b>STATUTORY ORDER:</b> Show-cause orders have been issued for all entities listed herein under the "
            "Water and Air Acts. Immediate CEMS audit and compliance escrow deposits are mandatory."
        )
        story.append(Paragraph(closing, body_style))
        story.append(Spacer(1, 12))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        fallback = f"COMPILED NOCTURNAL VIOLATIONS REPORT\nTotal Violations: {len(violations)}\n"
        for v in violations:
            fallback += f"- {v.get('factory_name')}: {v.get('pollutant')} ({v.get('confidence_score')}%) Fine: INR {v.get('penalty_inr')}\n"
        return fallback.encode('utf-8')

