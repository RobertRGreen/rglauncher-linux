// MIT licensed; original project build helper. See LICENSE.
// Capture native SVG geometry and turn strokes into genuine filled contours.
// GTK3's symbolic loader rewrites fills; open stroked primitives are unsuitable.
// No pixels are traced and no raster image is embedded in the generated asset.
#include <QGuiApplication>
#include <QSvgRenderer>
#include <QPaintEngine>
#include <QPainter>
#include <QPainterPath>
#include <QPainterPathStroker>
#include <QFile>
#include <QSaveFile>
#include <QXmlStreamReader>
#include <QStringList>
#include <iostream>

class OutlineEngine : public QPaintEngine {
public:
    OutlineEngine() : QPaintEngine(QPaintEngine::AllFeatures) {}
    QPen pen;
    QBrush brush;
    QTransform transform;
    QList<QPainterPath> pieces;

    bool begin(QPaintDevice *) override { return true; }
    bool end() override { return true; }
    Type type() const override { return QPaintEngine::User; }
    void updateState(const QPaintEngineState &s) override {
        if (s.state() & DirtyPen) pen = s.pen();
        if (s.state() & DirtyBrush) brush = s.brush();
        if (s.state() & DirtyTransform) transform = s.transform();
    }
    void capture(const QPainterPath &path, bool allowFill = true) {
        if (allowFill && brush.style() != Qt::NoBrush && brush.color().alpha())
            pieces.append(transform.map(path));
        if (pen.style() != Qt::NoPen && pen.brush().style() != Qt::NoBrush && pen.color().alpha()) {
            QPainterPathStroker stroker;
            stroker.setWidth(pen.widthF() > 0 ? pen.widthF() : 1);
            stroker.setCapStyle(pen.capStyle());
            stroker.setJoinStyle(pen.joinStyle());
            stroker.setMiterLimit(pen.miterLimit());
            pieces.append(transform.map(stroker.createStroke(path)));
        }
    }
    void drawPath(const QPainterPath &path) override { capture(path); }
    void drawRects(const QRectF *rects, int count) override {
        for (int i = 0; i < count; ++i) { QPainterPath p; p.addRect(rects[i]); capture(p); }
    }
    void drawRects(const QRect *rects, int count) override {
        for (int i = 0; i < count; ++i) { QPainterPath p; p.addRect(rects[i]); capture(p); }
    }
    void drawEllipse(const QRectF &rect) override { QPainterPath p; p.addEllipse(rect); capture(p); }
    void drawEllipse(const QRect &rect) override { drawEllipse(QRectF(rect)); }
    void drawLines(const QLineF *lines, int count) override {
        for (int i = 0; i < count; ++i) { QPainterPath p; p.moveTo(lines[i].p1()); p.lineTo(lines[i].p2()); capture(p, false); }
    }
    void drawLines(const QLine *lines, int count) override {
        for (int i = 0; i < count; ++i) { QLineF line(lines[i]); drawLines(&line, 1); }
    }
    void drawPolygon(const QPointF *points, int count, PolygonDrawMode mode) override {
        if (!count) return;
        QPainterPath p; p.moveTo(points[0]);
        for (int i = 1; i < count; ++i) p.lineTo(points[i]);
        if (mode != PolylineMode) p.closeSubpath();
        capture(p, mode != PolylineMode);
    }
    void drawPixmap(const QRectF &, const QPixmap &, const QRectF &) override {}
};

class OutlineDevice : public QPaintDevice {
public:
    mutable OutlineEngine engine;
    QPaintEngine *paintEngine() const override { return &engine; }
    int metric(PaintDeviceMetric m) const override {
        switch (m) {
        case PdmWidth: case PdmHeight: return 24;
        case PdmWidthMM: case PdmHeightMM: return 6;
        case PdmDpiX: case PdmDpiY: case PdmPhysicalDpiX: case PdmPhysicalDpiY: return 96;
        case PdmDepth: return 32;
        case PdmNumColors: return 0;
        case PdmDevicePixelRatio: return 1;
        case PdmDevicePixelRatioScaled: return devicePixelRatioFScale();
        default: return 0;
        }
    }
};

QString number(qreal value) {
    if (qAbs(value) < .000005) value = 0;
    return QString::number(value, 'f', 5);
}

QString svgPath(const QPainterPath &p) {
    QString out;
    for (int i = 0; i < p.elementCount(); ++i) {
        auto e = p.elementAt(i);
        if (e.type == QPainterPath::MoveToElement) out += "M" + number(e.x) + " " + number(e.y);
        else if (e.type == QPainterPath::LineToElement) out += "L" + number(e.x) + " " + number(e.y);
        else if (e.type == QPainterPath::CurveToElement) {
            auto b = p.elementAt(++i), c = p.elementAt(++i);
            out += "C" + number(e.x) + " " + number(e.y) + " " + number(b.x) + " " + number(b.y) + " " + number(c.x) + " " + number(c.y);
        }
    }
    return out;
}

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    int converted = 0;
    for (int i = 1; i < argc; ++i) {
        QString filename = QString::fromLocal8Bit(argv[i]);
        QFile input(filename);
        if (!input.open(QIODevice::ReadOnly)) return 2;
        QByteArray original = input.readAll(); input.close();
        QSvgRenderer renderer(original);
        if (!renderer.isValid()) return 3;
        OutlineDevice device;
        QPainter painter(&device);
        renderer.render(&painter, QRectF(0, 0, 24, 24));
        painter.end();
        if (device.engine.pieces.isEmpty()) return 4;
        QString title = "Icon", titleId = "icon-title";
        QXmlStreamReader xml(original);
        while (!xml.atEnd()) {
            xml.readNext();
            if (xml.isStartElement() && xml.name() == QLatin1String("title")) {
                titleId = xml.attributes().value("id").toString(); title = xml.readElementText(); break;
            }
        }
        QString contours;
        // Keep each exact curve. Boolean path union unnecessarily flattens curves
        // at this small coordinate scale and changes overlapping antialiasing.
        for (const auto &piece : device.engine.pieces) {
            QString fillRule = piece.fillRule() == Qt::OddEvenFill ? "evenodd" : "nonzero";
            contours += "<path fill=\"currentColor\" stroke=\"none\" fill-rule=\"" + fillRule + "\" d=\"" + svgPath(piece) + "\"/>";
        }
        QString svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" role=\"img\" aria-labelledby=\"" + titleId.toHtmlEscaped() + "\"><title id=\"" + titleId.toHtmlEscaped() + "\">" + title.toHtmlEscaped() + "</title>" + contours + "</svg>\n";
        QSaveFile output(filename);
        if (!output.open(QIODevice::WriteOnly) || output.write(svg.toUtf8()) < 0 || !output.commit()) return 5;
        ++converted;
    }
    std::cout << converted << " symbolic SVGs outlined natively" << std::endl;
    return 0;
}
