# Automated HyperOS Bootloader Unlocker

Helps you "brute force" the Xiaomi Community Forum bootloader unlock request at the daily reset, to avoid missing the limited request quota.

## Steps
1. Install the requirements:
```bash
pip3 install -r requirements.txt
```
2. Run the script. It will open your browser:
```bash
python3 hyperosunlocker.py
```
3. Get the `new_bbs_serviceToken` cookie value from DevTools.
4. Paste it into the script when prompted.
5. Wait until 00:00 Beijing time. The script fires the requests automatically.
6. Once done, add your device to Mi Unlock in Developer Tools.

Pass `--pressure` to fire the burst with parallel workers instead of a single request stream.

## If successful
Download the Mi Unlock Windows utility and finish the unlock process.

Otherwise, try again.
