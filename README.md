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

Sometimes, the server will actually approve your request, but not answer this back to the script, so it cannot know.
Once you obtained an unlock allowance, it must be used within a few days. I make it a habit to try the Mi Unlock in Developer Tools every few days when unlocking a device. Sometimes it will work despite the script having shown it failed. I cannot fix this without lowering the chances of success.

Be aware that Xiaomi may not like what you're doing. I haven't heard of people getting banned for hitting the unlock request hard, but Xiaomi's servers have returned "account blocked, try again in 3 days" for me before. `--pressure` makes this more likely. I usually run with `--precise`, which fires less requests, but spaces them apart. You can use both simultaneously, but I would do that on a throwaway account.

Be aware that to get an unlock allowance at all, your account must be at least 30 days old.

## If successful
Download the Mi Unlock Windows utility or MiUnlockTool: https://github.com/MiForge/MiUnlockTool
and finish the unlock process.

If you didn't get an unlock, try again tomorrow.

I have used this script to unlock 12 phones so far, one unlocked on the first try, one took me 6 days to get an unlock. The average was 3 days, I would guess.
