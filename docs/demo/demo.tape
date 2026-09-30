# Records docs/assets/demo.gif from the real invoice-agent executable.
# Regenerate with `make demo` (needs Docker). It records the PyInstaller build from `make exe`.
Output docs/assets/demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1280
Set Height 760
Set Padding 16
Set TypingSpeed 35ms
Set Theme "Dracula"

Hide
Type "export PATH=/opt/invoice-agent:$PATH PS1='$ ' && clear"
Enter
Show

Type "invoice-agent --version"
Enter
Wait@20s /\$\s*$/
Sleep 500ms
Type "invoice-agent process dataset/invoices/029_k07.pdf dataset/invoices/023_k01.pdf dataset/invoices/016_b04.pdf \"
Enter
Type "  --pos dataset/purchase_orders.json --receipts dataset/receipts.json"
Sleep 300ms
Enter
Wait@30s /\$\s*$/
Sleep 4s
Type "clear && invoice-agent eval | tail -n 24"
Sleep 300ms
Enter
Wait@60s /\$\s*$/
Sleep 5s
