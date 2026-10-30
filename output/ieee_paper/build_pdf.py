from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, FrameBreak, KeepTogether

OUT = Path("output/ieee_paper/Ecommerce_Customer_Behavior_IEEE_Paper.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)
W, H = letter
LM, RM, TM, BM = 0.68*inch, 0.68*inch, 0.42*inch, 0.48*inch
GAP = 0.23*inch
CW = (W-LM-RM-GAP)/2
NAVY = colors.HexColor("#172B4D")
INK = colors.HexColor("#171717")
GRAY = colors.HexColor("#4D5662")

ss = getSampleStyleSheet()
ss.add(ParagraphStyle(name="PaperTitle", parent=ss["Title"], fontName="Times-Bold", fontSize=21, leading=24, alignment=TA_CENTER, textColor=INK, spaceAfter=5))
ss.add(ParagraphStyle(name="Author", parent=ss["Normal"], fontName="Times-Roman", fontSize=10, leading=12, alignment=TA_CENTER, spaceAfter=4))
ss.add(ParagraphStyle(name="Abstract", parent=ss["BodyText"], fontName="Times-Roman", fontSize=8.5, leading=10.2, alignment=TA_JUSTIFY, spaceAfter=3))
ss.add(ParagraphStyle(name="Keywords", parent=ss["BodyText"], fontName="Times-Roman", fontSize=8, leading=9.5, alignment=TA_LEFT))
ss.add(ParagraphStyle(name="Formula", parent=ss["BodyText"], fontName="Times-Italic", fontSize=8.4, leading=11, alignment=TA_CENTER, textColor=INK, spaceBefore=2, spaceAfter=3))
ss.add(ParagraphStyle(name="Section", parent=ss["Heading1"], fontName="Times-Bold", fontSize=10.2, leading=12, alignment=TA_CENTER, textColor=INK, spaceBefore=5, spaceAfter=3, keepWithNext=True))
ss.add(ParagraphStyle(name="Subsection", parent=ss["Heading2"], fontName="Times-Italic", fontSize=9, leading=10.5, alignment=TA_LEFT, textColor=INK, spaceBefore=4, spaceAfter=2, keepWithNext=True))
ss.add(ParagraphStyle(name="Body", parent=ss["BodyText"], fontName="Times-Roman", fontSize=8.4, leading=10.2, alignment=TA_JUSTIFY, textColor=INK, spaceAfter=3))
ss.add(ParagraphStyle(name="Small", parent=ss["BodyText"], fontName="Times-Roman", fontSize=7.2, leading=8.5, alignment=TA_LEFT, textColor=INK))
ss.add(ParagraphStyle(name="TableHead", parent=ss["BodyText"], fontName="Times-Bold", fontSize=7, leading=8, textColor=INK))
ss.add(ParagraphStyle(name="TableCell", parent=ss["BodyText"], fontName="Times-Roman", fontSize=7, leading=8, textColor=INK))

class PaperDoc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=letter, leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM, title="An Integrated E-Commerce Customer Behavior Analytics Platform Using the Olist Dataset", author="Sahil")
        top_y = H-TM
        title_h = 3.05*inch
        title_frame = Frame(LM, top_y-title_h, W-LM-RM, title_h, leftPadding=3, rightPadding=3, topPadding=3, bottomPadding=2, id="title")
        first_h = top_y-title_h-BM-0.08*inch
        first_left = Frame(LM, BM, CW, first_h, leftPadding=2, rightPadding=4, topPadding=2, bottomPadding=0, id="firstleft")
        first_right = Frame(LM+CW+GAP, BM, CW, first_h, leftPadding=4, rightPadding=2, topPadding=2, bottomPadding=0, id="firstright")
        self.addPageTemplates([
            PageTemplate(id="First", frames=[title_frame, first_left, first_right], onPage=self.decorate),
            PageTemplate(id="Body", frames=[Frame(LM,BM,CW,H-TM-BM,leftPadding=2,rightPadding=4,topPadding=2,bottomPadding=0,id="left"), Frame(LM+CW+GAP,BM,CW,H-TM-BM,leftPadding=4,rightPadding=2,topPadding=2,bottomPadding=0,id="right")], onPage=self.decorate)
        ])
    def afterPage(self):
        if self.page == 1:
            self.handle_nextPageTemplate("Body")
    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 7)
        canvas.setFillColor(GRAY)
        canvas.drawRightString(W-RM, H-0.25*inch, "E-COMMERCE CUSTOMER BEHAVIOR ANALYTICS")
        canvas.drawCentredString(W/2, 0.25*inch, str(doc.page))
        canvas.restoreState()

def p(s, style="Body"):
    return Paragraph(s, ss[style])
def sec(s):
    return p(s, "Section")
def sub(s):
    return p(s, "Subsection")
def table(rows, widths):
    data=[]
    for ri,row in enumerate(rows):
        data.append([Paragraph(str(x), ss["TableHead"] if ri==0 else ss["TableCell"]) for x in row])
    t=Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
    t.setStyle(TableStyle([("LINEABOVE",(0,0),(-1,0),0.7,INK),("LINEBELOW",(0,0),(-1,0),0.5,INK),("LINEBELOW",(0,-1),(-1,-1),0.7,INK),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
    return t

story=[
    p("An Integrated E-Commerce Customer Behavior Analytics Platform Using the Olist Dataset","PaperTitle"),
    p("Sahil<br/><i>Big Data Analytics Project, India</i>","Author"),
    p("<b>Abstract—</b> E-commerce transaction logs contain signals about customer value, product affinity, geography, and sales dynamics, but these signals are difficult to use when data preparation, analytical code, and presentation are disconnected. This paper presents a local web-based analytics platform built with React, FastAPI, and PostgreSQL, adapted to the Brazilian E-Commerce Public Dataset by Olist. The system stores the nine relational Olist files in PostgreSQL, exposes compatibility views for a shared analytics model, and provides a user interface for sales dashboards, recency-frequency-monetary (RFM) analysis, K-Means customer segmentation, Apriori association rules, revenue forecasting, run history, and customer-to-customer recommendations. The recommender represents delivered purchases as product sets, ranks customers by Jaccard similarity, scores unseen products using neighbor similarity, and uses a popularity fallback. The contribution is an integrated analytics workflow rather than a new learning algorithm. Olist records describe historical Brazilian marketplace orders from 2016-2018; the application therefore does not establish current or India-specific consumer trends. No quantitative offline model results are claimed because reproducible evaluation metrics were not supplied.","Abstract"),
    p("<b>Index Terms—</b> e-commerce analytics, customer segmentation, RFM, association rule mining, collaborative filtering, Olist, PostgreSQL.","Keywords"),
    FrameBreak(),
    sec("I. INTRODUCTION"),
    p("Online retail systems collect order, item, payment, product, customer, seller, and review records. An analytical application must join these sources consistently and translate them into outputs users can inspect. This project implements that workflow as a locally operated web application over PostgreSQL using the public Olist dataset."),
    p("The engineering question is how a multi-table transaction dataset can support one interface for descriptive analytics, customer analysis, product affinity, forecasting, and personalized suggestions. The system uses a React and TypeScript frontend, a Python FastAPI service, and PostgreSQL. Analytical jobs execute through the API and persist results."),
    p("The contributions are: 1) an end-to-end application integrating data access, analytics, and visualization; 2) compatibility views that map Olist data to the existing analytics schema while preserving source tables; and 3) a purchase-history recommender with transparent peer similarity and a popularity fallback. This is a system implementation, not a novel-algorithm or commercial-impact claim."),
    sec("II. DATASET AND DATA MODEL"),
    p("The Brazilian E-Commerce Public Dataset by Olist contains approximately 100,000 orders from 2016-2018 and includes order, product, customer, payment, seller, review, and location information [1]. It is anonymized and distributed as nine CSV files. The tables are customers, geolocation, order items, payments, reviews, orders, products, sellers, and product category translations. Orders join to customer records and items; items join to products and sellers. Olist order-specific customer IDs can be linked across repeat purchases using customer_unique_id [1]."),
    table([["Table group","One row represents"],["Customers / sellers","Buyer or seller and location"],["Orders","Order status and lifecycle timestamps"],["Order items","One product line, seller, price, freight"],["Payments","Payment method, installments, amount"],["Reviews","Review score, comment, timestamps"],["Products","Catalog category and measurements"],["Geolocation","ZIP-prefix coordinate record"],["Translation","Portuguese and English category"]],[0.95*inch,2.35*inch]),
    sub("A. Compatibility and assumptions"),
    p("A SQL script creates read-only views customers, products, orders, and order_items, plus a stable integer customer mapping and persisted-result tables. Source Olist tables remain intact. The compatibility item view assigns quantity one because the source has no quantity column; item price is used as revenue and freight is excluded. The shared order view includes delivered, canceled, and unavailable statuses and flags the latter two as cancellations. Recommendations use delivered orders only. Values remain in Brazilian reais (BRL)."),
    sec("III. SYSTEM ARCHITECTURE"),
    p("The React and TypeScript frontend sends HTTP/JSON requests to a Python FastAPI backend. SQLAlchemy connects the API to PostgreSQL. Each analysis request creates a run record; a background task updates its status and saves results. Pages retrieve persisted results rather than fitting models on every view request."),
    table([["Layer","Implementation"],["Presentation","React, TypeScript, Vite, charts"],["API","Python, FastAPI, validation"],["Analytics","Pandas, NumPy, scikit-learn, mlxtend"],["Storage","PostgreSQL source tables, views, runs"]],[0.8*inch,2.5*inch]),
    p("The /api/health endpoint checks database access. /api/data-source reports detected schema, currency, data presence, and analytics readiness. Dashboard, customer, RFM, clustering, basket, forecast, recommendation, import, and run-history endpoints supply the UI. Jobs currently run in the API process, not a distributed queue."),
    sec("IV. ANALYTICAL METHODS"),
    sub("A. Dashboard and RFM"),
    p("The dashboard summarizes revenue, orders, customers, average order value, repeat purchases, cancellations, trends, products, and geography. RFM recency is days from the last purchase to the day after the dataset's last date; frequency is distinct orders; monetary value is non-canceled item revenue. Rank-based quintiles assign scores 1–5, with recency reversed so recent buyers score higher. Rule-based labels include Champions, Loyal Customers, At Risk, and Hibernating."),
    sub("B. Customer segmentation"),
    p("The pipeline applies log(1+x) to recency, frequency, and monetary features, then standardizes them. It evaluates k from 2 to 8, bounded by customer count, using silhouette score and selects the best unless k is fixed. K-Means uses a fixed seed; cluster profiles and a two-dimensional PCA projection are saved [2]. Clusters are descriptive, not ground-truth classes."),
    sub("C. Market-basket analysis"),
    p("The system forms invoice-by-product binary baskets, considers up to 150 frequent products by default, removes single-item baskets, and mines rules with Apriori. For X→Y, support is the share of transactions containing X∪Y, confidence estimates P(Y|X), and lift compares confidence with the marginal frequency of Y. Itemset length is bounded to three by default [3]."),
    sub("D. Revenue forecasting"),
    p("Daily revenue fills missing dates with zero. A Gradient Boosting Regressor uses weekday, day of month, month, lags of 28, 35, and 42 days, and a shifted seven-day rolling mean. The final 28 days form a chronological test window. Test MAE and RMSE are compared with a seasonal-naive baseline repeating the last observed weekday values. The model is refitted on all history for a forecast horizon up to 28 days [4]. At least 120 days plus the test window are required. No measured metrics are reported here."),
    sec("V. PERSONALIZED RECOMMENDATIONS"),
    p("The recommender uses delivered purchase histories as sets of distinct product IDs. For target customer u and another customer v, Jaccard similarity is:","Body"),
    p("J(u,v) = shared products in the two histories / all distinct products across both histories","Formula"),
    p("Up to 100 overlapping customers are retained. An unseen product receives a score equal to the sum of Jaccard similarities for neighbors who bought it.","Body"),
    p("Candidates rank by score and supporting-neighbor count. If peer candidates are absent, popular delivered items not in the target history are used."),
    p("The interface shows customer history, product IDs, translated categories, and the number of similar customers supporting a recommendation. Olist lacks readable product titles. The method uses purchases only, with no impressions, browsing, cart events, or explicit ratings. It is an interpretable baseline, not a production recommender."),
    sec("VI. IMPLEMENTATION AND WORKFLOW"),
    p("Operators import the nine CSVs into PostgreSQL in foreign-key order and run compatibility SQL after loading. The backend connection is configured in backend/.env. Pages include Dashboard, Customers & RFM, Segmentation, Products & Baskets, Recommendations, Forecasting, Data Import & Quality, and Run History. Users inspect data readiness, explore metrics, trigger analyses, and review persisted results. Workbook import is UCI-specific; Olist CSVs are loaded through pgAdmin. The project owner reports the Olist application and recommendations are working."),
    sec("VII. EVALUATION STATUS AND DISCUSSION"),
    p("This paper documents implementation and methodology. It does not claim measured accuracy, relevance, runtime, usability, or business impact. No held-out recommendation test, forecast metric output, or reproducible benchmark was provided. A populated interface demonstrates an execution path, not model quality."),
    p("A next evaluation should train on earlier delivered orders, hold out later interactions, and compare the recommender with popularity using Precision@K, Recall@K, catalog coverage, and customer-activity groups. Forecast MAE and RMSE should be reported against the seasonal baseline on fixed dates, in BRL. Clustering should include cluster sizes, profiles, and silhouette score. Actual database counts and date range should be captured from the loaded database."),
    p("Olist is historical and Brazil-specific, so it cannot substantiate current Indian trends. The compatibility layer simplifies quantity and excludes freight from item revenue. Sparse histories cause cold-start and limited-overlap cases. Geolocation, payments, and reviews are imported but are not central to current displayed analytics. Background jobs in the API process suit a local demonstration but are not resilient to process restarts."),
    sec("VIII. CONCLUSION"),
    p("This platform connects Olist relational data with customer analysis, product affinity, revenue forecasting, and personalized suggestions. Its engineering contribution integrates database setup, schema adaptation, persisted runs, API routes, and user-facing pages. The recommender uses Jaccard similarity on delivered histories and a popularity fallback. Quantitative evaluation, additional Olist signals, and a temporally newer dataset are important next steps."),
    sec("REFERENCES"),
    p("[1] Olist, “Brazilian E-Commerce Public Dataset by Olist,” Kaggle, 2018. [Online]. Available: kaggle.com/datasets/olistbr/brazilian-ecommerce","Small"),
    p("[2] J. MacQueen, “Some methods for classification and analysis of multivariate observations,” Proc. 5th Berkeley Symp. Math. Statist. Probability, vol. 1, 1967, pp. 281–297.","Small"),
    p("[3] R. Agrawal and R. Srikant, “Fast algorithms for mining association rules in large databases,” Proc. 20th Int. Conf. Very Large Data Bases, 1994, pp. 487–499.","Small"),
    p("[4] J. H. Friedman, “Greedy function approximation: A gradient boosting machine,” Annals of Statistics, vol. 29, no. 5, pp. 1189–1232, 2001, doi: 10.1214/aos/1013203451.","Small"),
]

doc=PaperDoc(str(OUT))
doc.build(story)
print(OUT.resolve())
