"""
core — Modelos de datos y extractores del Verificador de Ficheros de Corte.

Submódulos:
    modelos                CheckResult, Pieza, Bulto, OTData, DXFDoc.
    reglas_loader          Único punto de acceso a los archivos YAML.
    extractor_despiece     Lee el XLSX del DESPIECE desde BytesIO.
    extractor_etiquetas_ean Lee los CSVs ETIQUETAS y EAN LOGISTIC desde BytesIO.
    extractor_dxf          Lee ficheros DXF (CP1252) desde BytesIO.
    extractor_ot           Lee el PDF de la OT desde BytesIO con pdfplumber.
"""
