# Uttar Pradesh Panchayat Candidates Dataset - 2015, 2021

Code for creation of dataset of Panchayat candidates (village level) in the Indian state of Uttar Pradesh during the 2015 and 2021 elections.

> Note: The previous Google Sheet link is no longer available (returns HTTP 410 as of March 30, 2026).

## Getting updated source metadata

You can now pull a lightweight freshness snapshot directly from the official SEC UP candidate endpoint:

```bash
python update_data_snapshot.py
```

This writes `latest_snapshot.json` with:
- fetch timestamp (UTC)
- source URL
- currently listed post types on the official page

The Selenium scraping scripts in `2015_elections/` and `2021_elections/` have also been updated to use `https://sec.up.nic.in/...` URLs.

## List of Variables

<img width="500" alt="Screenshot 2022-01-24 at 10 01 28 PM" src="https://user-images.githubusercontent.com/16442168/150903096-99dc3a29-28a7-4404-9ea8-ccf84801d08a.png">
