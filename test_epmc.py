from app.connectors.europe_pmc import europe_pmc_search

def main():
    papers, total, nextc = europe_pmc_search("cancer", n=5)
    print("TOTAL:", total)
    print("RESULTS:", len(papers))
    print("NEXT CURSOR:", nextc)
    for i, p in enumerate(papers, 1):
        print(f"{i}. {p.id} | {p.year} | {p.title[:80]}")

    if nextc:
        papers2, total2, nextc2 = europe_pmc_search("cancer", n=5, cursor=nextc)
        print("\n--- PAGE 2 ---")
        print("TOTAL2:", total2)
        print("RESULTS2:", len(papers2))
        print("NEXT CURSOR 2:", nextc2)

if __name__ == "__main__":
    main()
