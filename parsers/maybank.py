from parsers.base import BaseParser
import pandas as pd
import pdfplumber
import re

class MaybankParser(BaseParser):
    def extract_transactions(self) -> pd.DataFrame:
        all_transactions = []
        current_transaction = None
        
        # Regex to match: 02/05/26 SALE DEBIT 2.62- 12.90
        # Group 1: Date (DD/MM/YY)
        # Group 2: Description part 1
        # Group 3: Amount
        # Group 4: Sign (+ or -)
        # Group 5: Balance
        tx_pattern = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})([+-])\s+([\d,]+\.\d{2})$")
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                    
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    match = tx_pattern.match(line)
                    if match:
                        # Save the previous transaction if exists
                        if current_transaction:
                            all_transactions.append(current_transaction)
                            
                        date_str = match.group(1)
                        desc = match.group(2).strip()
                        amt_str = match.group(3).replace(',', '')
                        sign = match.group(4)
                        
                        amount = float(amt_str)
                        if sign == '-':
                            amount = -amount
                            
                        balance_str = match.group(5).replace(',', '')
                        balance = float(balance_str)
                        
                        current_transaction = {
                            'Date': date_str,
                            'Description': desc,
                            'Amount': amount,
                            'Balance': balance
                        }
                    else:
                        # If we are currently building a transaction, this might be extra description
                        if current_transaction:
                            # Stop if we hit standard footer notes or page headers
                            if "Perhatian" in line or "All items and balances" in line or line.startswith("(") or "STATEMENT DATE" in line or "BEGINNING BALANCE" in line:
                                pass # Probably footer or header, ignore
                            else:
                                current_transaction['Description'] += f" {line}"
                                
        if current_transaction:
            all_transactions.append(current_transaction)
            
        df = pd.DataFrame(all_transactions)
        if not df.empty:
            return df[['Date', 'Description', 'Amount']]
        return pd.DataFrame(columns=['Date', 'Description', 'Amount'])
        
    def extract_ending_balance(self) -> float:
        last_balance = 0.0
        tx_pattern = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})([+-])\s+([\d,]+\.\d{2})$")
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                lines = text.split('\n')
                for line in lines:
                    match = tx_pattern.match(line.strip())
                    if match:
                        last_balance = float(match.group(5).replace(',', ''))
                        
        return last_balance
