from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#11172a")
PURPLE = colors.HexColor("#7c5cfc")


def create_pdf_report(scan, result):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("PatternIQ analysis report", styles["Title"]),
        Paragraph(f"Dataset: {escape(scan['filename'])} · Created: {escape(scan['created_at'])}", styles["Normal"]),
        Spacer(1, 16),
    ]
    overview = result["overview"]
    table_data = [
        ["Dataset overview", "Result"],
        ["Rows", f"{overview['rows']:,}"],
        ["Columns", str(overview["columns"])],
        ["Numeric / categorical", f"{overview['numeric_columns']} / {overview['categorical_columns']}"],
        ["Missing cells", f"{overview['missing_cells']:,}"],
        ["Duplicate rows", f"{overview['duplicate_rows']:,}"],
        ["Detected anomalies", f"{result['anomalies']['count']:,}" if result["anomalies"]["available"] else "Not available"],
        ["Clusters discovered", str(result["clusters"]["count"]) if result["clusters"]["available"] else "Not available"],
    ]
    story.extend([Table(table_data, colWidths=[2.6 * inch, 3.8 * inch]), Spacer(1, 16)])
    story.append(Paragraph("Key findings", styles["Heading2"]))
    for insight in result["insights"]:
        story.append(Paragraph(f"• {escape(insight)}", styles["BodyText"]))
        story.append(Spacer(1, 5))
    story.extend([Spacer(1, 8), Paragraph("Suggested next steps", styles["Heading2"])])
    for recommendation in result["recommendations"]:
        story.append(Paragraph(f"• {escape(recommendation)}", styles["BodyText"]))
        story.append(Spacer(1, 5))

    if result["clusters"]["available"]:
        story.extend([Spacer(1, 12), Paragraph("Cluster profile", styles["Heading2"])])
        cluster_rows = [["Cluster", "Records", "Share", "Notable standardized features"]]
        for cluster in result["clusters"]["sizes"]:
            feature_text = ", ".join(feature["name"] for feature in cluster["features"]) or "No strongly distinguishing feature"
            cluster_rows.append([str(cluster["id"]), f"{cluster['size']:,}", f"{cluster['share']}%", feature_text])
        story.append(Table(cluster_rows, colWidths=[0.7 * inch, 0.9 * inch, 0.8 * inch, 4 * inch]))
        drawing = Drawing(450, 150)
        chart = VerticalBarChart()
        chart.x = 35
        chart.y = 25
        chart.width = 380
        chart.height = 105
        chart.data = [[cluster["size"] for cluster in result["clusters"]["sizes"]]]
        chart.categoryAxis.categoryNames = [
            f"Group {cluster['id'] + 1}" for cluster in result["clusters"]["sizes"]
        ]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(1, max(cluster["size"] for cluster in result["clusters"]["sizes"]))
        chart.valueAxis.valueStep = max(1, chart.valueAxis.valueMax // 4)
        chart.bars[0].fillColor = PURPLE
        chart.valueAxis.labels.fontSize = 8
        chart.categoryAxis.labels.fontSize = 8
        drawing.add(chart)
        story.append(drawing)
    if result["correlations"]:
        story.extend([Spacer(1, 12), Paragraph("Strong numeric relationships", styles["Heading2"])])
        corr_rows = [["Feature A", "Feature B", "Correlation"]]
        corr_rows.extend([[item["first"], item["second"], f"{item['value']:.3f}"] for item in result["correlations"][:10]])
        story.append(Table(corr_rows, colWidths=[2.2 * inch, 2.2 * inch, 1.3 * inch]))

    story.extend([
        Spacer(1, 18),
        Paragraph(
            "Method note: clusters are exploratory K-Means groups; unusual records are Isolation Forest candidates, not proof of errors or fraud. "
            "No model accuracy score is reported because this is unsupervised analysis without labeled ground truth.",
            styles["Italic"],
        ),
    ])

    def paint(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, letter[1] - 0.22 * inch, letter[0], 0.22 * inch, fill=1, stroke=0)
        canvas.setFillColor(PURPLE)
        canvas.rect(0, 0, letter[0], 0.08 * inch, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=paint, onLaterPages=paint)
    output.seek(0)
    return output
