from modules.advanced_replace import advanced_replace

assert advanced_replace("1菲2菲3菲4菲5菲", "菲", "F", "1~-1") == "1F2F3F4F5F"
assert advanced_replace("1菲2菲3菲4菲5菲", "菲", "F", "4~-1") == "1菲2菲3菲4F5F"
assert advanced_replace("1菲2菲3菲4菲5菲", "菲", "F", "-1~4|2") == "1菲2F3菲4F5F"
assert advanced_replace("1菲2菲3菲4菲5菲", "菲", "F", "2~4") == "1菲2F3F4F5菲"
assert advanced_replace("abcabcabc", "abc", "X", "2") == "abcXabc"
assert advanced_replace("abcabcabc", "abc", "X", "-1") == "abcabcX"
print("ALL PASSED")
