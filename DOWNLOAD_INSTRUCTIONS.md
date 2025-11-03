# Download LinkedIn Network CSV

## Quick Download Options

### Option 1: Double-Click (Easiest) 🖱️
Just **double-click** the `download.bat` file in your project folder.

### Option 2: Run in Command Prompt 💻
1. Open **Command Prompt** (cmd.exe, NOT PowerShell)
2. Navigate to your project:
   ```cmd
   cd "C:\Users\User\Documents\1Work\GhostTeam\Work\Weekly Demo's\Cursor for your network"
   ```
3. Run:
   ```cmd
   python download_csv.py
   ```

### Option 3: Browser Download 🌐
Just click this link (it will download automatically):
```
https://web-production-e31ba.up.railway.app/export/network.csv
```

## File Location

The CSV file will be saved to:
```
data\network.csv
```

Full path:
```
C:\Users\User\Documents\1Work\GhostTeam\Work\Weekly Demo's\Cursor for your network\data\network.csv
```

## What You'll Get

- ✅ **150 contacts** exported
- ✅ **12 columns** of data
- ✅ **~469 KB** file size
- ✅ Includes: Full Name, Email, LinkedIn URL, Company, Skills, Education, and more

## Troubleshooting

### If Python command doesn't work:
1. Make sure Python is installed: `python --version`
2. Install requests library: `pip install requests pandas`
3. Or use the browser download option instead

### If download fails:
- Check your internet connection
- Verify the API key is correct
- Try the browser download option

## Files Created

- `download_csv.py` - Python download script
- `download.bat` - Windows batch file (double-click to run)
- `DOWNLOAD_INSTRUCTIONS.md` - This file

