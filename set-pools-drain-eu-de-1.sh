#!/bin/bash
# Set pools to drain state in eu-de-1
# Usage: source your openrc first, then run this script
#   source ~/openrc-eu-de-1.sh
#   ./set-pools-drain-eu-de-1.sh

set -e

POOLS=(
  "cinder-volume-kvm-stnpca1-st048@stnpca1_st048_nfs#10.246.51.49:/cinder_001"
  "cinder-volume-kvm-stnpca1-st056@stnpca1_st056_nfs#10.246.47.55:/cinder_001"
  "cinder-volume-kvm-stnpca1-st071@stnpca1_st071_nfs#10.246.51.89:/cinder_001"
  "cinder-volume-kvm-stnpca1-st077@stnpca1_st077_nfs#10.246.51.97:/cinder_001"
  "cinder-volume-kvm-stnpca1-st078@stnpca1_st078_nfs#10.246.51.109:/cinder_001"
  "cinder-volume-kvm-stnpca1-st083@stnpca1_st083_nfs#10.246.43.61:/cinder_001"
  "cinder-volume-kvm-stnpca1-st097@stnpca1_st097_nfs#10.246.51.105:/cinder_001"
  "cinder-volume-kvm-stnpca1-st104@stnpca1_st104_nfs#10.246.43.67:/cinder_001"
  "cinder-volume-kvm-stnpca1-st105@stnpca1_st105_nfs#10.246.51.51:/cinder_001"
  "cinder-volume-kvm-stnpca1-st108@stnpca1_st108_nfs#10.246.47.63:/cinder_001"
  "cinder-volume-kvm-stnpca1-st117@stnpca1_st117_nfs#10.246.43.15:/cinder_001"
  "cinder-volume-kvm-stnpca2-st048@stnpca2_st048_nfs#10.246.51.182:/cinder_001"
  "cinder-volume-kvm-stnpca2-st071@stnpca2_st071_nfs#10.246.51.91:/cinder_001"
  "cinder-volume-kvm-stnpca2-st078@stnpca2_st078_nfs#10.246.51.111:/cinder_001"
  "cinder-volume-kvm-stnpca2-st097@stnpca2_st097_nfs#10.246.51.107:/cinder_001"
  "cinder-volume-kvm-stnpca2-st104@stnpca2_st104_nfs#10.246.43.69:/cinder_001"
  "cinder-volume-kvm-stnpca2-st108@stnpca2_st108_nfs#10.246.47.75:/cinder_001"
  "cinder-volume-kvm-stnpca2-st117@stnpca2_st117_nfs#10.246.43.17:/cinder_001"
  "cinder-volume-kvm-stnpca3-st047@stnpca3_st047_nfs#10.246.47.57:/cinder_001"
  "cinder-volume-kvm-stnpca3-st048@stnpca3_st048_nfs#10.246.51.184:/cinder_001"
  "cinder-volume-kvm-stnpca3-st055@stnpca3_st055_nfs#10.246.51.190:/cinder_001"
  "cinder-volume-kvm-stnpca3-st078@stnpca3_st078_nfs#10.246.51.113:/cinder_001"
  "cinder-volume-kvm-stnpca3-st090@stnpca3_st090_nfs#10.246.47.61:/cinder_001"
  "cinder-volume-kvm-stnpca3-st108@stnpca3_st108_nfs#10.246.47.77:/cinder_001"
  "cinder-volume-kvm-stnpca3-st117@stnpca3_st117_nfs#10.246.43.19:/cinder_001"
  "cinder-volume-kvm-stnpca4-st028@stnpca4_st028_nfs#10.246.51.87:/cinder_001"
  "cinder-volume-kvm-stnpca4-st055@stnpca4_st055_nfs#10.246.51.192:/cinder_001"
  "cinder-volume-kvm-stnpca4-st077@stnpca4_st077_nfs#10.246.51.99:/cinder_001"
  "cinder-volume-kvm-stnpca4-st078@stnpca4_st078_nfs#10.246.51.115:/cinder_001"
  "cinder-volume-kvm-stnpca4-st108@stnpca4_st108_nfs#10.246.47.79:/cinder_001"
  "cinder-volume-kvm-stnpca5-st065@stnpca5_st065_nfs#10.246.51.194:/cinder_001"
  "cinder-volume-kvm-stnpca5-st077@stnpca5_st077_nfs#10.246.51.101:/cinder_001"
  "cinder-volume-kvm-stnpca5-st078@stnpca5_st078_nfs#10.246.51.117:/cinder_001"
  "cinder-volume-kvm-stnpca5-st108@stnpca5_st108_nfs#10.246.47.81:/cinder_001"
  "cinder-volume-kvm-stnpca6-st065@stnpca6_st065_nfs#10.246.51.196:/cinder_001"
  "cinder-volume-kvm-stnpca6-st071@stnpca6_st071_nfs#10.246.51.93:/cinder_001"
  "cinder-volume-kvm-stnpca6-st077@stnpca6_st077_nfs#10.246.51.103:/cinder_001"
  "cinder-volume-kvm-stnpca6-st078@stnpca6_st078_nfs#10.246.51.119:/cinder_001"
  "cinder-volume-kvm-stnpca7-st071@stnpca7_st071_nfs#10.246.51.95:/cinder_001"
)

echo "Setting ${#POOLS[@]} pools to drain state in eu-de-1"
echo "=========================================="

success=0
failed=0

for pool in "${POOLS[@]}"; do
  echo -n "Setting drain: $pool ... "
  if cinder set-pool-state "$pool" drain 2>&1; then
    echo "OK"
    ((success++))
  else
    echo "FAILED"
    ((failed++))
  fi
done

echo ""
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo "Total pools: ${#POOLS[@]}"
echo "Successful: $success"
echo "Failed: $failed"

if [ $failed -gt 0 ]; then
  exit 1
fi
