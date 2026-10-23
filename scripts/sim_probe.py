import base64, json, requests
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.hash import Hash
from solders.instruction import Instruction, AccountMeta
from solders.message import Message
from solders.transaction import Transaction
from solders.system_program import transfer, TransferParams
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
RPC="https://api.mainnet-beta.solana.com"
CB=Pubkey.from_string("ComputeBudget111111111111111111111111111111")
def loaded_limit(n):  # ComputeBudgetInstruction::SetLoadedAccountsDataSizeLimit = tag 4, u32 LE
    return Instruction(CB, bytes([4])+n.to_bytes(4,"little"), [])
payer=Pubkey.from_string("HEL1USMZKAL2odpNBj2oCjffnFGaYwmbGmyewGv1e2TU")  # funded system account, simulation only
lock=Keypair().pubkey()  # fresh, non-existent
def sim(ixs, label):
    msg=Message(ixs, payer)
    tx=Transaction.new_unsigned(msg)
    raw=base64.b64encode(bytes(tx)).decode()
    r=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":"simulateTransaction","params":[raw,{"encoding":"base64","sigVerify":False,"replaceRecentBlockhash":True,"commitment":"processed"}]},timeout=30).json()
    v=r.get("result",{}).get("value",r)
    print(label, "| err:", v.get("err"), "| CU:", v.get("unitsConsumed"), "| fee?", v.get("fee"), "| logs:", (v.get("logs") or [])[-2:])
base=[set_compute_unit_limit(600), set_compute_unit_price(1000), loaded_limit(32768)]
sim(base+[transfer(TransferParams(from_pubkey=payer,to_pubkey=lock,lamports=0))], "0-lamport -> non-existent")
sim(base+[transfer(TransferParams(from_pubkey=payer,to_pubkey=payer,lamports=0))], "0-lamport self")
sim([set_compute_unit_limit(450), set_compute_unit_price(0), loaded_limit(32768), transfer(TransferParams(from_pubkey=payer,to_pubkey=lock,lamports=0))], "limit=450 exact")
sim([set_compute_unit_limit(600), transfer(TransferParams(from_pubkey=payer,to_pubkey=lock,lamports=0))], "no loaded-limit ix (default 64MiB)")
