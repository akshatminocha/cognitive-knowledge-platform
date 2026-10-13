import os
import random
import csv
import json
import sqlite3
import pandas as pd
from faker import Faker
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

fake = Faker()

DATA_DIR = "../../../data"
UNSTRUCTURED_DIR = os.path.join(DATA_DIR, "unstructured")
STRUCTURED_DIR = os.path.join(DATA_DIR, "structured")
SQL_DB_PATH = os.path.join(DATA_DIR, "enterprise.db")

os.makedirs(UNSTRUCTURED_DIR, exist_ok=True)
os.makedirs(STRUCTURED_DIR, exist_ok=True)

def generate_policy_pdf(filename, title, content):
    filepath = os.path.join(UNSTRUCTURED_DIR, filename)
    c = canvas.Canvas(filepath, pagesize=letter)
    c.drawString(100, 750, title)
    text = c.beginText(40, 700)
    text.setFont("Helvetica", 12)
    
    for line in content.split('\n'):
        text.textLine(line)
        
    c.drawText(text)
    c.save()
    print(f"Generated PDF: {filepath}")

def generate_technical_markdown(filename, title, content):
    filepath = os.path.join(UNSTRUCTURED_DIR, filename)
    with open(filepath, 'w') as f:
        f.write(f"# {title}\n\n")
        f.write(content)
    print(f"Generated Markdown: {filepath}")

def generate_product_catalog_csv(num_products=50):
    filepath = os.path.join(STRUCTURED_DIR, "products.csv")
    products = []
    categories = ['Electronics', 'Office Supplies', 'Software', 'Furniture']
    
    for _ in range(num_products):
        products.append({
            'product_id': fake.uuid4(),
            'name': fake.catch_phrase(),
            'category': random.choice(categories),
            'price': round(random.uniform(10.0, 5000.0), 2),
            'description': fake.sentence(),
            'stock_level': random.randint(0, 1000)
        })
    
    df = pd.DataFrame(products)
    df.to_csv(filepath, index=False)
    print(f"Generated CSV: {filepath}")
    return df

def generate_employees_sql(num_employees=20):
    conn = sqlite3.connect(SQL_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT,
        department TEXT,
        role TEXT,
        start_date TEXT
    )
    ''')
    
    departments = ['Sales', 'Engineering', 'HR', 'Marketing', 'Executive']
    
    employees = []
    for _ in range(num_employees):
        employees.append((
            fake.name(),
            fake.email(),
            random.choice(departments),
            fake.job(),
            str(fake.date_this_decade())
        ))
        
    cursor.executemany('INSERT INTO employees (name, email, department, role, start_date) VALUES (?, ?, ?, ?, ?)', employees)
    conn.commit()
    conn.close()
    print(f"Generated SQL Table: employees in {SQL_DB_PATH}")

def generate_data():
    print("Generating Synthetic Data...")
    
    # 1. Policies (PDF)
    vacation_policy = """
    1. Vacation Time
    All employees are eligible for 20 days of paid vacation per year.
    Vacation requests must be submitted 2 weeks in advance.
    
    2. Sick Leave
    Employees get 10 days of sick leave annually.
    Doctor's note required for more than 3 consecutive days.
    """
    generate_policy_pdf("hr_policy_2024.pdf", "Corporate HR Policy 2024", vacation_policy)
    
    # 2. Tech Docs (Markdown)
    api_docs = """
    ## Authentication
    All API requests require a Bearer Token.
    
    ## Endpoints
    - GET /api/v1/users: List all users
    - POST /api/v1/users: Create a new user
    
    ## Errors
    - 401: Unauthorized
    - 403: Forbidden
    - 404: Not Found
    """
    generate_technical_markdown("api_documentation.md", "Internal API Documentation", api_docs)
    
    # 3. Product Catalog (CSV)
    generate_product_catalog_csv()
    
    # 4. Employees (SQL)
    generate_employees_sql()
    
    print("Data Generation Complete.")

if __name__ == "__main__":
    generate_data()
