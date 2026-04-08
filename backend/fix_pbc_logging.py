import re

pbc_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(pbc_path, "r", encoding="utf-8") as f:
    text = f.read()

new_except = """        except Exception as e:
            print(f"Error in Pullback Engine for {df.attrs.get('symbol', 'Unknown')}: {e}")
            import traceback
            traceback.print_exc()"""

text = text.replace("        except Exception as e:\n            # print(f\"Error in Pullback Engine: {e}\")", new_except)

with open(pbc_path, "w", encoding="utf-8") as f:
    f.write(text)

print("PBC logging enabled in ta_intraday.py")
