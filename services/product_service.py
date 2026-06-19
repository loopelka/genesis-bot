import openpyxl

PRODUCTS_FILE = "products.xlsx"

def load_products():
    wb = openpyxl.load_workbook(PRODUCTS_FILE)
    ws = wb.active
    products = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0]:
            products.append({
                "name": row[0],
                "description": row[1],
                "price": row[2],
            })
    return products
