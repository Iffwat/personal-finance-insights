from parsers.base import BaseParser
import pandas as pd
import pdfplumber
import re

class GenericBankParser(BaseParser):
    def extract_transactions(self) -> pd.DataFrame:
        all_rows = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        # Very basic heuristic: if row has a date-like string and a number, it might be a transaction
                        # This is highly generic and will likely need tuning for a specific bank.
                        if len(row) >= 3:
                            # Filter out empty or header rows
                            # Match dates like MM/DD/YYYY or MM-DD-YY
                            if row[0] and re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', str(row[0])):
                                all_rows.append(row)
                                
        if not all_rows:
            return pd.DataFrame(columns=['Date', 'Description', 'Amount'])
            
        # Create a raw dataframe
        df = pd.DataFrame(all_rows)
        
        # Rename first 3 columns
        num_cols = len(df.columns)
        col_names = ['Date', 'Description', 'Amount']
        if num_cols > 3:
            col_names += [f'Col_{i}' for i in range(3, num_cols)]
        elif num_cols < 3:
            return pd.DataFrame(columns=['Date', 'Description', 'Amount'])
            
        df.columns = col_names
        return df[['Date', 'Description', 'Amount']]
        
    def extract_ending_balance(self) -> float:
        # Extracting the correct balance is highly bank-specific.
        # This is a placeholder.
        return 0.0
