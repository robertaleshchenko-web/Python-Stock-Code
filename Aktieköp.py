import sys  # Importerar sys för att kunna avsluta programmet med sys.exit
import datetime  # Importerar datetime för att skapa och hantera datumobjekt
import math  # Importerar math för att kontrollera NaN-värden med math.isnan
try:
    import yfinance # Försöker importera yfinance för att hämta marknadsdata från Yahoo
    import pandas # Försöker importera pandas som yfinance kan använda internt
except Exception:
    yfinance = None  # Om import misslyckas, sätt yf till None för att indikera att yfinance inte finns
    pandas = None  # Om import misslyckas, sätt pd till None för att indikera att pandas inte finns


def läs_fundamenta(fil: str) -> dict:
    #Läser fundamenta från fil med formaten: Namn;soliditet;pe;ps
    data = {} #Tom dict
    with open(fil, "r", encoding="utf-8") as f: #Öppnar filen
        for rad in f: #Loopar för varje rad
            rad = rad.strip() #Tar bort all whitespace
            delar = rad.split(";") #Delar upp raden till olika delar
            if len(delar) != 4: #Ser till så att det finns exakt 4 delar
                print(f"Ignorerar rad (fel format fundamenta): {rad}")
                continue
            
            namn = delar[0] #Första fältet är namnet
            try: #Försöker konverta de numeriska talen till floats
                soliditet = float(delar[1].replace(",", "."))
                pe = float(delar[2].replace(",", "."))
                ps = float(delar[3].replace(",", "."))
            except Exception:
                print(f"Ignorerar rad (felaktiga siffror fundamenta): {rad}")
                continue
            data[namn] = {"soliditet": soliditet, "pe": pe, "ps": ps} #Formen av dicten
    return data

def läs_kurser(fil: str) -> dict:
    #Läser kursfil där varje rad är: Namn;ÅÅÅÅ-MM-DD;pris
    data = {} #Tom dict
    with open(fil, "r", encoding="utf-8") as f: #Öppnar filen
        for rad in f: #Loopar för varje rad
            rad = rad.strip() #Tar bort all whitespace
            delar = rad.split(";") #Delar upp raden till olika delar
            if len(delar) != 3: #Ser till så att det finns exakt 3 delar
                print(f"Ignorerar rad (fel format kurser): {rad}")
                continue
            namn = delar[0] #Första fältet är namnet
            try: #Försöker att konvertera numeriska delarna till deras respektive form
                datum = datetime.date.fromisoformat(delar[1]) #Gör datum strängan till ett datum objekt
                pris = float(delar[2].replace(",", "."))
            except Exception: #Vid eventuellt fel
                print(f"Ignorerar rad (ogiltiga värden kurser): {rad}") #Visar var det fanns fel
                continue
            data.setdefault(namn, []).append((datum, pris)) #Lägger till våran tuple till listan av företag och är default ifall fundamenta fick inget
    for namn in list(data.keys()): #Loopar för varje aktie kurs 
        data[namn] = sorted(data[namn], key=lambda x: x[0]) #Sorterar kursen från äldst till nyaste
    return data

def läs_omx(fil: str) -> list:
    #Läser OMX-data filen med formaten: ÅÅÅÅ-MM-DD;pris
    data = [] #Tom lista
    with open(fil, "r", encoding="utf-8") as f:
        for rad in f:
            rad = rad.strip()
            if not rad or rad.startswith("#"):
                continue
            delar = rad.split(";")
            if len(delar) != 2:
                print(f"Ignorerar rad (fel format omx): {rad}")
                continue
            try:
                datum = datetime.date.fromisoformat(delar[0])
                pris = float(delar[1].replace(",", "."))
            except Exception:
                print(f"Ignorerar rad (ogiltiga värden omx): {rad}")
                continue
            data.append((datum, pris))
    return sorted(data, key=lambda x: x[0])


class Aktie:  #Här defineras våran klass som representerar en aktie
    def __init__(self, namn, fundamenta, kurser):
        self.namn = namn  #Sparar namnet i objektet
        self.soliditet = fundamenta.get("soliditet") if fundamenta else None  #Hämtar soliditet från fundamenta om finns annars None
        self.pe = fundamenta.get("pe") if fundamenta else None  # Hämtar p/e från fundamenta om finns annars None
        self.ps = fundamenta.get("ps") if fundamenta else None  # Hämtar p/s från fundamenta om finns annars None
        self.kurser = kurser if kurser else []  #Sparar sorterad lista med (datum, pris) annars en tom lista
        self.pris_nu = None  # Plats för aktuellt pris hämtat från Yahoo
        self.yf_pe = None  # Plats för Yahoo P/E
        self.yf_ps = None  # Plats för Yahoo P/S
        self.ticker = None  # Plats för ticker-symbol
        self._beta_lista = None  # Cache för beräknade betan för att inte

    def kursutveckling(self):  #Beräknar procentuell förändring från första till sista kurs
        if not self.kurser:  #Kontroll: kräver minst en kurs
            raise ValueError("Ingen kursdata")  #Fel om ingen kursdata
        start = self.kurser[0][1]  #Första kursvärdet
        slut = self.kurser[-1][1]  #Sista kursvärdet
        if start == 0:
            raise ZeroDivisionError("Startkurs är noll")  #Fell om noll-division görs
        return (slut - start) / start * 100.0  #Procentförändringen

    def min_max(self):  #Returnerar min och max pris från kurslistan
        if not self.kurser:  #Kontroll att kurslista inte är tom
            raise ValueError("Ingen kursdata")  #Fel om tom
        priser = [p for (_d, p) in self.kurser]  #Tar in pris värden prisvärden utan att ta datum
        return min(priser), max(priser)  # Returnerar min och max

    def beta(self, omx):  #Beräknar beta värdet
        if self._beta_lista is not None:  #Om tidigare beräknade betor finns
            return self._beta_lista  #Returnerar förvaring
        if not self.kurser:  #Kontroll att aktien har kursdata
            raise ValueError("Ingen kursdata")  #Fel om tom
        if not omx:  #Kontroll att OMX-data finns
            raise ValueError("Ingen OMX-data")  #Fel om tom
        omx_dict = {d: p for (d, p) in omx}  #Gör en dict för att snabbt hita OMX-priser per datum
        aktie_datum = [d for (d, _p) in self.kurser]  #Lista över datum för aktiens kurser
        gemensamma = sorted(set(aktie_datum).intersection(set(omx_dict.keys())))  #Gemensamma datum mellan aktie och OMX
        if len(gemensamma) < 2:  #Kräver minst två gemensamma datum för att beräkna procentförändring
            raise ValueError("För få gemensamma datum för beta")  #Fel om för det är för få datum
        första = gemensamma[0]  #Första gemensamma datum
        sista = gemensamma[-1]  #Sista gemensamma datum
        akt_start = next(p for (d, p) in self.kurser if d == första)  #Hittar aktiens startpris
        akt_slut = next(p for (d, p) in self.kurser if d == sista)  # Hittar aktiens slutpris
        omx_start = omx_dict[första]  # OMX-startpris
        omx_slut = omx_dict[sista]  # OMX-slutpris
        if akt_start == 0 or omx_start == 0:
            raise ZeroDivisionError("Startkurs noll i beta-beräkningen")  #Fell om noll-division görs
        akt_pct = (akt_slut - akt_start) / akt_start * 100.0  #Beräknar aktiens procentförändring
        omx_pct = (omx_slut - omx_start) / omx_start * 100.0  #Beräknar OMX procentförändring
        if omx_pct == 0:
            raise ZeroDivisionError("OMX procentförändring är noll")  #Fell om noll-division görs
        beta_värde = akt_pct / omx_pct  #Beräknar beta värdet
        self._beta_lista = beta_värde  #Sparar i "cachen" för att slippa omräkning
        return beta_värde

def hämta_yf_ticker(ticker):  #Hämtar data från Yahoo för en given ticker och returnerar en dict
    #Returnerar dict med keys: 'pris_nu','yf_pe','yf_ps','history'
    if yfinance is None: 
        raise RuntimeError("yfinance/pandas saknas")  #Fel om yfinance är inte installerat
    ut = {"pris_nu": None, "yf_pe": None, "yf_ps": None, "history": []}  #Gör en retur-dict
    tk = None  #Placeholder för ticker-objekt
    try:
        tk = yfinance.Ticker(ticker)  #Skapar ett Ticker-objekt
    except Exception:
        raise RuntimeError(f"Kunde inte skapa Ticker för {ticker}: {Exception}")  #Fel om konstruktion misslyckas
    try:
        info = tk.info  #Försöker läsa info-attributet
    except Exception:
        info = {}  #Sätter info till tom dict vid fel
    try:
        if isinstance(info, dict):  #Om info är en dict, hämta data från fälten:
            ut["yf_pe"] = info.get("trailingPE")  #Hämtar trailing P/E om finns
            ut["yf_ps"] = info.get("priceToSalesTrailing12Months")  #Hämtar P/S om finns
    except Exception:
        ut["yf_pe"] = None  #Vid fel, sätt None
        ut["yf_ps"] = None  #Vid fel, sätt None
    #Nuvarande pris
    try:
        pris = None  #Placeholder för pris
        if hasattr(tk, "fast_info") and tk.fast_info:  #Om fast_info finns i Ticker-objektet
            fi = tk.fast_info
            pris = fi.get("last_price") or fi.get("lastPrice")  #Försöker att få senaste pris
        if pris is None:  #Om pris inte fanns genom fast info
            hist1 = tk.history(period="1d")  #Hämta senaste dagens historik
            if not hist1.empty: #Om senare dagens pris är inte tom
                pris = float(hist1["Close"].iloc[-1])  #Ta sista close priset
        ut["pris_nu"] = float(pris) if pris is not None else None  #Sätt pris i retur-dicten
    except Exception:
        ut["pris_nu"] = None  #Vid fel, sätt None
    #1 månads historia
    try:
        hist30 = tk.history(period="1mo", interval="1d")  #Hämtar 1 månads daglig historik
        if not hist30.empty:  #Om DataFrame inte är tom
            for idx, row in hist30.iterrows():  #Loopar över varje rad för datan för en månad
                dt = idx.to_pydatetime().date()  #Konvertera idx till datum
                stängning = row.get("Close", None)  # Hämta Close-kolumnens värde
                if stängning is None or (isinstance(stängning, float) and math.isnan(stängning)):
                    continue  #Hoppa över rad om close saknas eller är NaN
                ut["history"].append((dt, float(stängning)))  #Lägger till tuplen i historiken
    except Exception:
        ut["history"] = []  #Vid fel, sätt historia till en tom list
    return ut #Returnera retur-dict definerad tidigare

def yahoo_meny(aktier, ticker_mapp):  #Funktion som frågar efter ticker och uppdaterar eller skapar Aktie objekt
    #Frågar användaren efter en ticker, hämtar data från Yahoo och visar det.
    #Om aktien finns uppdateras objektet, annars skapas ett nytt och läggs till i 'aktier'
    
    if yfinance is None: 
        raise RuntimeError("yfinance/pandas saknas")  #Fel om yfinance är inte installerat
    tick = input("Ange ticker (t.ex. INVE-B.ST) eller tom för att avbryta: ").strip()  #Frågar efter ticker
    if not tick:  #Om användaren trycker enter utan att skriva
        print("Avbröt Yahoo-hämtning.")
        return
    tick = tick.upper() 
    try:
        res = hämta_yf_ticker(tick)  #Hämtar data från Yahoo
    except Exception:
        print(f"Fel vid hämtning från Yahoo: {Exception}")  #Informerar om fel
        return
    print(f"--- Yahoo data för {tick} ---\n"  #Yahoo menyn
    f"Aktuellt pris (Yahoo): {res.get('pris_nu')}\n"  #Aktuellt pris
    f"P/E (Yahoo): {res.get('yf_pe')}\n"  #Yahoo P/E
    f"P/S (Yahoo): {res.get('yf_ps')}\n"  #Yahoo P/S
    "Senaste historik (datum, stängning):")
    for d, p in res.get("history", [])[:10]:  #Skriver ut upp till 10 historiska priser
        print(f"  {d} -> {p}")  #Visar datum och pris
    
    namn = None  #Placeholder för företagsnamn att associera med tickern
    #Om tickern finns i ticker_mapp som värde, hitta tillhörande namn
    for n, t in ticker_mapp.items():  #Loopar över ticker_mapp (namn --> ticker)
        if t == tick:  #Om värdet matchar angiven ticker
            namn = n  #Spara namnet
            break
    if namn is None:  #Om tickern inte redan är kopplad
        namn = input("Ange namn på företaget att associera med tickern (exakt som i fundamenta/kurser eller nytt namn): ").strip()  #Frågar efter namn
        if not namn:  #Om inget namn angavs
            print("Ingen namn angavs — avbryter.")
            return
    ticker_mapp[namn] = tick  #Uppdaterar/lagrar mapping namn->ticker
    mål = next((x for x in aktier if x.namn == namn or x.ticker == tick), None)  #Försöker hitta befintligt Aktie-objekt
    if mål:  # Om ett objekt hittades
        mål.ticker = tick  #Sätt tickern i objektet
        if res.get("pris_nu") is not None:
            mål.pris_nu = res["pris_nu"]  #Uppdaterar aktuellt pris
        if res.get("yf_pe") is not None:
            mål.yf_pe = res["yf_pe"]  #Uppdaterar P/E
        if res.get("yf_ps") is not None:
            mål.yf_ps = res["yf_ps"]  #Uppdaterar P/S
        if res.get("history"):
            mål.kurser = sorted(res["history"], key=lambda t: t[0])  #Ersätter kurslistan med Yahoo-historik
        print(f"Uppdaterade {mål.namn} med Yahoo-data.")  #Bekräftelse
    else:  #Om inga par hittades
        fundamenta = {"soliditet": None, "pe": None, "ps": None}  #Tomma fundamenta för nytt objekt
        ny = Aktie(namn, fundamenta, sorted(res["history"], key=lambda t: t[0]) if res.get("history") else [])  #Skapar nytt Aktie-objekt
        ny.ticker = tick  #Ticker
        ny.pris_nu = res.get("pris_nu")  #Aktuellt pris
        ny.yf_pe = res.get("yf_pe")  # Yahoo P/E
        ny.yf_ps = res.get("yf_ps")  # Yahoo P/S
        aktier.append(ny)  # Lägg till nytt objekt i listan
        print(f"Skapade nytt Aktie-objekt för {namn} och lade till i listan.")

def fråga_int(fråga, övre):  #Funktion som frågar användaren efter ett heltal inom ett intervall
    while True:  #Loopar tills giltig inmatning
        svar = input(fråga + " ").strip()  #Läser in och trimmar input
        try:
            v = int(svar)  #Försöker konverterar till int
            if 1 <= v <= övre:  #Kontrollerar att värdet ligger inom intervallet
                return v  #Returnerar giltigt värde
            print(f"Fel! Ange ett heltal mellan 1 och {övre}.") #Fel vid värde utanför interval
        except ValueError:
            print("Fel! Ange ett giltigt heltal.")  #Felmeddelande vid icke-heltal

def aktie_lista(aktier):
    if not aktier: #Om tomt
        print("Ingen aktiedata tillgänglig.")
        return None
    for i, a in enumerate(aktier, start=1): #Returnerar en aktie lista med nummer från 1
        print(f"{i}. {a.namn}")
    idx=fråga_int("Vilken aktie vill du välja? (ange nummer)", len(aktier))
    return aktier[idx-1]

def visa_Fundamenta(aktier):
    aktie=aktie_lista(aktier)
    if aktie is None: #Om tom
        return
    
    print("--- Fundamental analys ---")
    print(f"Soliditet (fil): {aktie.soliditet}\n"  #Soliditet från fil
        f"P/E (fil): {aktie.pe}\n"  #P/E från fil
        f"P/S (fil): {aktie.ps}")  #P/S från fil
    if aktie.yf_pe is not None:
        print(f"P/E (Yahoo): {aktie.yf_pe}")  #Yahoo P/E
    if aktie.yf_ps is not None: 
        print(f"P/S (Yahoo): {aktie.yf_ps}")  #Yahoo P/S
    if aktie.pris_nu is not None:
        print(f"Aktuellt pris (Yahoo): {aktie.pris_nu}")  #Aktuellt pris
            
def visa_Teknisk(aktier,omx):
    aktie=aktie_lista(aktier)
    if aktie is None:
        return
    print("--- Teknisk analys ---")
    try:
        pct = aktie.kursutveckling()  #Beräknar kursutveckling
        mn, mx = aktie.min_max()  #Kallar på min och max
        b = aktie.beta(omx)  # Beräknar betavärde
        print(f"Kursutveckling: {pct:.2f}%\n"  #Kursutveckling
        f"Lägsta kurs: {mn} kr\n"  #Lägsta kurs
        f"Högsta kurs: {mx} kr\n"  #Högsta kurs
        f"Betavärde: {b:.4f}\n")  #Beräknad beta
        #Yahoo-fält
        if aktie.pris_nu is not None:
            print(f"Aktuellt pris (Yahoo): {aktie.pris_nu}")  #Yahoo pris
        if aktie.yf_pe is not None:
            print(f"P/E (Yahoo): {aktie.yf_pe}")  #Yahoo P/E
        if aktie.yf_ps is not None:
            print(f"P/S (Yahoo): {aktie.yf_ps}")  #Yahoo P/S
    except Exception:
        print("Fel vid teknisk analys:", Exception)    

def visa_Beta(aktier, omx):
    print("--- Rangordning efter betavärde ---")
    betor = [] #Skapar en tom lista
    for a in aktier: #Loopar för varje aktie
        try:
            b = a.beta(omx) #Försöker beräkna beta
            betor.append((a.namn, b)) #Tillägger till listan
        except Exception:
            print(f"Kunde inte beräkna beta för {a.namn}: {Exception}")
    if not betor:
        print("Ingen beta-data kunde beräknas.")
        return
    betor.sort(key=lambda x: x[1], reverse=True) #Sorterar från störst till minst
    for i, (n, b) in enumerate(betor, start=1): #Visar en lista med nummer från 1
        print(f"{i}. {n} - {b:.4f}")

def huvud_meny(aktier, omx, ticker_mapp):
    while True:  #Huvudmenyloop
        print("\n----- Meny -----\n"  
        "1. Fundamental analys (långsiktigt köp)\n"  
        "2. Teknisk analys (kortsiktigt köp)\n"  
        "3. Rangordning av aktier efter betavärde\n"  
        "4. Yahoo Finance (hämta en ticker och lägg till/uppdatera)\n" 
        "5. Avsluta")       
        val = fråga_int("Vilket alternativ vill du välja? (1-5)", 5)  #Meny val
        if val == 1:  #Fundamental analys
            visa_Fundamenta(aktier)
        elif val == 2: #Teknisk analys
            visa_Teknisk(aktier,omx)
        elif val == 3: #Beta rangordning
            visa_Beta(aktier,omx)
        elif val == 4: #Yahoo Finance
            yahoo_meny(aktier,ticker_mapp)
        elif val == 5: #Avsluta
            print("Hejdå! Programmet stängs.")
            break 
        else:
            print("Felaktigt val, försök igen.")  #Säkerhets ifall
        
def main():
    print("Välkommen till aktieprogrammet!")  # Hälsningsmeddelande
    try:
        fundamenta = läs_fundamenta("fundamenta.txt")  #Läser fundamenta från fil
        kurser = läs_kurser("kurser.txt")  #Läser kurser från fil
        omx = läs_omx("omx.txt")  #Läser OMX-data från fil
    except FileNotFoundError:
        print("Fel! Kunde inte läsa in filer:", FileNotFoundError)  #Felmeddelande om filer saknas
        sys.exit(1)  #Avslutar programmet
    
    aktier = []  #Skapar en tom lista för Aktie-objekt
    for namn in fundamenta.keys():  #Loopar över företag som finns i fundamenta
        if namn not in kurser:  #Om motsvarande kursdata saknas
            print(f"Varning! Ingen kursdata för {namn} - hoppar över.")
            continue
        a = Aktie(namn, fundamenta[namn], kurser[namn])  #Skapar ett Aktie-objekt
        aktier.append(a)  #Lägger till objektet till listan
    
    #Om det finns kurser för namn som saknas i fundamenta, lägg till med tomma fundamenta
    for namn in kurser.keys():  #Loopar över företag som finns i kursfilen
        if namn not in [a.namn for a in aktier]:  #Om företaget inte redan lagts till
            a = Aktie(namn, {"soliditet": None, "pe": None, "ps": None}, kurser[namn])  #Skapar objekt med tomma fundamenta
            aktier.append(a)  #Lägger till objektet i listan
    
    ticker_mapp = {}  #Skapar en tom dict för mapping mellan företagsnamn och tickers för Yahoo

    huvud_meny(aktier,omx,ticker_mapp) #Kallar på huvudmenyn
    
if __name__ == "__main__":
    main()
