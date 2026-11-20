#!/usr/bin/env bash
# Kiem CHI DOC tren host A sau khi ap gate v2 (ADR-12). Khong doi trang thai,
# khong in credential, khong doc aodh.conf. Chay boi TV1 (ubuntu, can sudo de
# doc journal cua devstack@aodh-evaluator):
#   bash verify-gate-v2-ro.sh [so_phut]      # mac dinh 30 phut gan nhat
# Ket qua mong doi sau khi ap v1 + v2:
#   - HEAD = e07aeb6d118b4b9099947028e6e809a6bdd8fe22
#   - git diff --stat: dung 1 file aodh/evaluator/gnocchi.py
#   - sha256 gnocchi.py = SHA_V1_V2 (v2.1; neu = SHA_V1 thi gate v2.1 CHUA ap / da lui)
#   - devstack@aodh-evaluator active, 0 dong Traceback trong cua so
set -u

AODH=/opt/stack/aodh
MIN=${1:-30}
SHA_UPSTREAM=d63b84f4c61cd8f05a4f76488bc179720edf461592e94bb0c825cba91dd01ca0
SHA_V1=8bc8a1153ce36c4732236834e173bb86cdf52d0fbc43170ce47eb331ad1dbb38
SHA_V1_V2=3d2bed8247161e54cfdaad29efcc6f5e040cc6011c251e32c000dda2798a56fb   # v2.1 (v2 cu 443751e5 khong dung nua)
UNIT=devstack@aodh-evaluator

echo "== thoi diem (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "== HEAD aodh"
git -C "$AODH" rev-parse HEAD
echo "== git diff --stat (mong doi 1 file)"
git -C "$AODH" diff --stat
echo "== git status --short"
git -C "$AODH" status --short

echo "== sha256 gnocchi.py dang nam tren dia"
got=$(sha256sum "$AODH/aodh/evaluator/gnocchi.py" | cut -d' ' -f1)
echo "$got"
case "$got" in
  "$SHA_V1_V2") echo "KET LUAN: upstream + v1 + gate v2.1" ;;
  443751e5126a08e0abf237238f2148c8d3f088bc6fddecd0fdeb3e4fc76a77e7) echo "KET LUAN: gate v2 CU (co lo hong trending) - lui va ap v2.1" ;;
  "$SHA_V1") echo "KET LUAN: upstream + v1 (gate v2 CHUA ap hoac da lui)" ;;
  "$SHA_UPSTREAM") echo "KET LUAN: upstream sach (khong co ban va nao)" ;;
  *) echo "KET LUAN: KHONG KHOP ban nao da biet - dung lai, bao TV1/TV2" ;;
esac

echo "== evaluator dang chay ma nao (thoi diem khoi dong so voi mtime file)"
systemctl is-active "$UNIT"
systemctl show -p ActiveEnterTimestamp "$UNIT"
stat -c 'mtime gnocchi.py: %y' "$AODH/aodh/evaluator/gnocchi.py"

echo "== journal ${MIN} phut gan nhat"
log=$(sudo journalctl -u "$UNIT" --since "-${MIN}min" --no-pager -o cat 2>/dev/null)
echo "so dong Traceback: $(printf '%s' "$log" | grep -c 'Traceback')"
echo "so dong campus-gate reject (tong): $(printf '%s' "$log" | grep -c 'campus-gate reject=')"
echo "-- theo ly do va loai alarm (op=gt la high, op=lt la low):"
printf '%s' "$log" | grep -o 'campus-gate reject=[a-z_0-9]* op=[a-z]* n=[0-9]*' | sort | uniq -c
echo "so dong campus-gate hold=equivocal (v2.1, giu insufficient data): $(printf '%s' "$log" | grep -c 'campus-gate hold=equivocal')"
printf '%s' "$log" | grep -o 'campus-gate hold=equivocal op=[a-z]* n=[0-9]* trend=[a-z]*' | sort | uniq -c
echo "-- 10 dong reject gan nhat (chi phan campus-gate):"
printf '%s' "$log" | grep 'campus-gate reject=' | tail -n 10 | grep -o 'campus-gate reject=.*' | cut -c1-160
