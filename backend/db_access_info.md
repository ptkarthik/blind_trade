# Database Access Details
The database for this application is **SQLite**, which is a file-based database. 
- **File Path**: `C:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\blind_trade.db`
- **Tool Recommendation**: SQL Server Management Studio (SSMS) is for Microsoft SQL Server and will not work directly with this file. I recommend using a dedicated SQLite GUI:
  - **DB Browser for SQLite** (Free, open-source, and very easy to use).
  - **SQLiteStudio**.
  - **VS Code Extension**: If you use VS Code, the "SQLite Viewer" extension is excellent for quick checks.

# Progress Report
I am currently investigating why the scan appears stuck and why his results aren't appearing in the UI. 
- **Current Observation**: The UI shows a scan at 15% (281 / 2229), but the database only shows an older "completed" job from earlier this morning. This indicates the current scan's state might not be reaching the database correctly.
- **Next Steps**:
  - Check worker logs for database sync errors.
  - Verify if the `intraday_engine.py` background sync loop is hanging.
  - Force-clear possibly stuck job states if necessary.
