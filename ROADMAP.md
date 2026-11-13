# ALIEN TRACKER — porovnanie a plán rozvoja

[Certain] Audit k 13. 11. 2026 sa týka aplikácie COLMAP_Tracker / ALIEN TRACKER.
Stav vychádza z miestneho kódu; porovnanie z oficiálnych stránok výrobcov.
Nejde o porovnávací benchmark presnosti solverov ani o sľub termínov.

[Likely] Najväčšia medzera je možnosť zistiť, prečo tracking zlyhal, opraviť
konkrétne body a prepočítať výsledok. Prioritou má byť spoľahlivý cyklus
„track → skontroluj → oprav → znovu vyrieš → exportuj“.

## Hotové v tejto úprave

[Certain] Vstup obrazovej sekvencie: priečinok PNG/JPG/JPEG/EXR/TIFF, prirodzené
zoradenie, voľba zdrojového FPS, asynchrónny náhľad a existujúce ovládanie prehrávania.
Projekt uchová presné poradie snímok; tracking vytvorí pracovné kópie a EXR/TIFF prevedie
do PNG. TIFF podporuje .tif aj .tiff; overené sú 8/16-bitové RGB snímky a zachovanie
16-bitovej presnosti pracovných kópií. Overené sú formáty, prehrávanie, znovuotvorenie, overlay aj príprava snímok
pre COLMAP. HDR grading a výber EXR vrstiev nie sú súčasťou. Čaká na používateľský test.

[Certain] P0 je implementované a integračne overené; používateľ 13. 11. 2026
povolil pokračovanie do P1. Zahŕňa zoznam objektov, Show/Lock, premenovanie/duplikáciu/mazanie,
Frame selected, spoločné Undo/Redo, krokovanie, In/Out/loop/rýchlosť,
zoom/pan/100 %/lupu, autosave/recovery, recent projects a relink. Zapracovaná je
aj sivá téma Shadow s modrým výberom a ikonami v Scene & objects.

[Certain] Prvý bod P1 — dátový základ — je implementovaný; používateľ povolil
pokračovanie k overlayu chyby. Import zachová image/point ID, XY pozorovania, pôvodné XYZ a obojsmerné väzby
trackov, rozlišuje nepripojené a neplatné pozorovania. Plné dáta sú oddelené od
preriedeného viewportu. Panel Track data zobrazuje počty po frameoch a umožňuje
prechod na frame. Testovacia scéna obsahuje 13 836 119 pozorovaní; načítanie trvalo
približne 16 sekúnd.

[Certain] Druhý bod P1 — overlay reprojekčnej chyby — je implementovaný a čaká
na používateľský test. Solved frames zobrazuje meranie, projekciu a spojnicu chyby,
farby podľa pixelovej odchýlky, pôvodnú alebo upravenú kameru a filter/limit značiek.
Pracuje v priestore importovaného obrazu; pri Source video žiada prepnúť na presnú
solved snímku. Súhrnné metriky, graf chyby a ručné 2D opravy ešte nie sú súčasťou
tohto kroku. Ďalší bod počká na test a schválenie.

[Certain] Na požiadanie používateľa je pridané jednoduchšie ručné doladenie kamery:
ťahanie označení osí X/Y/Z a RX/RY/RZ s okamžitým náhľadom, Shift pre jemný pohyb,
voľba rýchlosti, jeden krok Undo za ťah a Esc na zrušenie. Ide o opravu pózy kamery;
editácia 2D markerov zostáva samostatným plánovaným krokom. Táto úprava čaká na test.

[Certain] Doplnok Only this frame uzamkne ručnú opravu kamery na zvolený solved
frame. Pri prezeraní ostatných snímok sú opravy zablokované; cieľ sa mení explicitne
cez Use current frame. Overené je zachovanie oboch susedných kamier, existujúcich
opráv, Undo/Redo a návrat na cieľovú snímku. Režim čaká na používateľský test.

[Certain] Translation graph je rozdelený na podpísané zmeny ΔX/ΔY/ΔZ v osiach
Z-up rekonštrukcie. Dá sa izolovať jedna os, porovnať pôvodná/upravená krivka
a prepnúť späť na celkovú veľkosť posunu (Translation total). Overené sú záporné
hodnoty, normalizácia podľa medzier medzi framami, výber frameu a obnova po Undo.

[Certain] Interpolate ±5 zachová opravený stred a interpoluje päť susedných framov
na každej strane k pevným vonkajším kamerám. Rozsah je nastaviteľný od ±5 po ±100;
pri krajoch sa skráti, chýbajúce kamery preskočí. Celý zásah má jeden krok Undo/Redo.
Ide o explicitnú úpravu rozsahu aj pri zapnutom Only this frame; číselné polia
a ťahanie stále menia iba stred. Overené sú rotácie cez 180°, zachovanie stredu
a okolia, uloženie aj export. Táto úprava čaká na používateľský test.

[Certain] Prehrávanie zdieľa pripravenú geometriu objektov medzi oboma náhľadmi
a opätovne využíva GPU buffery objektov aj povrchového meshu. Pri lokálnom meraní
4K/29,97 fps klipu so 16 objektmi klesol priemerný čas 3D kreslenia z 2,93 na
0,62 ms a kreslenia video okna z 6,39 na 4,44 ms. Obe merania zobrazovali približne
30 fps; prevod video snímkov zostáva najdrahšou časťou a výkon závisí od počítača.

- [Certain] E prepína posun, R rotáciu a T rovnomernú mierku. G ostáva aliasom posunu.
- [Certain] Scale má štvorcové držadlo; mení objekt alebo celú scénu okolo jej existujúceho pivotu. Esc vráti rozpracovanú zmenu. Nejde o nezávislé škálovanie X/Y/Z.
- [Certain] Space aj Play po dohraní spustia zdrojové video aj solved frames od začiatku. Uprostred záznamu pokračujú z pozastavenej pozície.
- [Certain] Skratky rešpektujú editáciu polí, dialógy, výber bodov podlahy a rozpracovaný drag. Tlačidlo pri dohraní zdrojového videa zobrazí Play.

## Čo ukazuje porovnanie

| Program | Overené schopnosti | Medzera v ALIEN TRACKERi |
| --- | --- | --- |
| Blender | [Certain] Automatický aj ručný tracking, maskovanie a rekonštrukcia kamery; čistenie trackov podľa dĺžky a reprojekčnej chyby. [VFX](https://www.blender.org/features/vfx/), [Clean Tracks](https://docs.blender.org/manual/ko/latest/movie_clip/tracking/clip/editing/track.html) | [Certain] Máme automatický solve, statickú masku a opravy 3D kamery. Chýba ručný editor 2D pozorovaní, čistenie jednotlivých trackov a ich opätovné použitie pri solve. |
| SynthEyes | [Certain] Tracking kamery a objektov, interaktívne spresňovanie, stabilizácia a exporty do viacerých 3D/compositing aplikácií. [Oficiálny prehľad](https://borisfx.com/products/syntheyes/) | [Certain] Kamera sa opravuje numericky po solve; chýba tracking pohybujúcich sa objektov, stabilizácia a širší export kamery. Máme export do Blenderu a PLY meshu. |
| 3DEqualizer | [Certain] Tracking dopredu/dozadu, animované spline masky, krivky chyby kamery aj jednotlivých bodov a editor segmentov trackov. [Technické špecifikácie](https://www.3dequalizer.com/index.php?item=tech_spec&site=start) | [Certain] Náš graf meria pohyb/skok kamery, nie chybu projekcie voči nameraným bodom. Masku nemožno animovať; segmenty 2D trackov nie sú editovateľné. |
| Mocha Pro | [Certain] Planárny tracking, opravy driftu cez AdjustTrack, rotoskopia, stabilizácia, deformovateľný PowerMesh a 3D camera solve. [Oficiálny prehľad](https://borisfx.com/products/mocha-pro/) | [Certain] Nemáme planárne plochy, corner pin, roto ani deformovateľné tracky. Náš rekonštruovaný 3D povrch je iná funkcia ako PowerMesh. |

[Likely] Z Blenderu sa oplatí prevziať kontrolu a čistenie trackov, z 3DEqualizeru
prehľad chyby, zo SynthEyes opravný workflow a exporty. Planárny tracking z Mochy
má zmysel ako samostatná neskoršia vetva pre výmenu obrazoviek a vkladanie grafiky.

## Východiskový audit pred implementáciou P0

[Certain] Tabuľka zachytáva pôvodné medzery. Dokončené položky P0 sú uvedené
vyššie; zvyšné medzery zostávajú plánované.

| Oblasť | Overený stav |
| --- | --- |
| Projekty | [Certain] New/Open/Save/Save as, prázdny štart, upozornenie na neuložené zmeny a atomický zápis. Chýba autosave, obnova po páde, recent projects, relink presunutých médií a zabalenie projektu s médiami. |
| Prehrávanie | [Certain] Space, časová os, zdroj/solved režim, prednačítavanie a GPU overlay. Chýbajú explicitné kroky ±1 frame, Home/End, Go to frame, loop, In/Out, rýchlosť a viditeľné údaje o vynechaných snímkach/cache. |
| Obraz | [Certain] Náhľad sa prispôsobuje oknu. Chýba zoom/pan obrazu, 100 % pixelový pohľad, lupa a stabilizovaný detail tracku. |
| 3D úpravy | [Certain] Výber kliknutím, posun/rotácia/mierka, Global/Local, cube/cone, osový gizmo, floor z vybraných bodov. Chýba všeobecné Undo/Redo, multiselect, duplikovanie, pomenovanie a skrývanie jednotlivých objektov, snapping a import referenčnej geometrie. |
| Diagnostika | [Certain] Počty kamier/bodov, log a graf pohybu kamery. Chýba chyba na frame/track, pokrytie obrazu, životnosť trackov, prehľad neregistrovaných frameov a porovnanie verzií solve. |
| Opravy | [Certain] Korekcia 3D pózy, interpolácia medzi susedmi, reset a samostatné Undo korekcií; floor má vlastné Undo. Chýba jednotná história a spätné odovzdanie ručne opravených 2D bodov solveru. |
| Výpočet | [Certain] COLMAP/GLOMAP, statická maska, FPS, veľkosť obrazu, susedné snímky, GPU a Stop. Nový job vytvára nový priečinok; chýba resume dokončených krokov a správa variantov. |
| Povrch/export | [Certain] Približný Poisson povrch zo sparse bodov, shading, PLY a Blender export. Chýba dense reconstruction, textúrovanie, export kontrolného videa a samostatný export kamery do ďalších formátov. |

## Poradie implementácie

[Likely] Náročnosť S/M/L/XL vyjadruje relatívny rozsah, nie počet dní. Etapy sú
návrh; okrem položiek označených ako hotové sa týmto dokumentom neimplementujú.

### 1. P0 — základné ovládanie a ochrana práce

| Balík | Návrh | Rozsah | Podmienka dokončenia |
| --- | --- | --- | --- |
| Transport | [Likely] Šípky ±1 frame, Home/End, číslo frameu, loop, In/Out a 0,25×–2×. Zjednotiť mapovanie času zdroja na extrahované snímky. | M | Pozastavené krokovanie je presné; video, kamera, graf aj export zodpovedajú rovnakému času. Otestované aj 29,97 fps a odlišné tracking FPS. |
| Kontrola obrazu | [Likely] Zoom pod kurzorom, pan, Fit/100 %, lupa a rýchle vypnutie overlayov. | M | Overlay sedí na rovnakom pixeli pri každom zoome aj po resize. |
| História úprav | [Likely] Ctrl+Z/Ctrl+Shift+Z pre objekty, transformácie, floor a kamerové opravy; jeden drag = jeden krok. | M | Undo/Redo vráti presné hodnoty aj po zmene výberu; správne obnoví stav neuložených zmien. |
| Obnova práce | [Likely] Periodický autosave mimo hlavného súboru, recovery pri štarte, recent projects a relink chýbajúcich súborov. | M | Simulovaný pád umožní obnovu; neprepíše sa posledný ručný save; presunutý projekt ide znovu pripojiť. |
| Základné objekty | [Likely] Delete, Duplicate, Rename, Hide/Lock, Frame selected, zoznam objektov a prehľad skratiek. | S–M | Zmena sa prejaví v 3D, obraze, save/reopen aj exporte a dá sa vrátiť. |

### 2. P1 — vidieť, kde a prečo solve zlyháva

[Certain] Pôvodný import preskakoval 2D pozorovania. Teraz ich `track_data.py`
zachováva aj s väzbami a kontrolou konzistencie; `pipeline.read_model()` poskytuje
plné dáta aplikácii a ľahký režim pre export a meshing.

- [Certain] **Implementované, pokračovanie povolené:** stabilné image/point ID, track ID = point ID, pozorovanie = image ID + index, XY, platnosť, frame a čas odvodený z tracking FPS; plné diagnostické dáta oddelené od viewportu. Pôvodné mediálne PTS sa zo samotného COLMAP TXT nedajú obnoviť.
- [Certain] **Implementované, čaká na test:** overlay meranie/projekcia/spojnica a zelená ≤1 px, žltá ≤3 px, červená >3 px; výber pôvodnej/upravenej kamery a limit prednostne najväčších chýb. Používa príslušný model obrazu a presné Solved frames, nemieša originál a undistorted súradnice.
- [Likely] Zobraziť medián/RMS a vysoký percentil chyby v pixeloch, počty inlierov, dĺžku trackov a rozloženie bodov po obraze. V grafe označiť chýbajúce kamery a skokom prejsť na podozrivý frame. Rozsah M.
- [Likely] Umožniť vybrať bod v obraze aj 3D a vidieť jeho históriu. Na veľkých modeloch načítavať detaily postupne. Rozsah M.

[Likely] Hotové bude, keď synteticky poškodené pozorovanie označí správny frame
aj track a vypočítaná pixelová chyba súhlasí s nezávislou projekčnou kontrolou.
Malá priemerná chyba sama osebe nemá znamenať „dobrý solve“; treba kontrolovať aj
pokrytie, kontinuitu a použiteľnosť kamery pri vložení testovacieho objektu.

### 3. P1 — ručné opravy a opätovný solve

- [Likely] Pridávanie/posúvanie 2D markerov, oblasť vzoru a hľadania, track dopredu/dozadu, stop pri strate istoty a opätovné pripojenie po zakrytí. Rozsah L.
- [Likely] Disable/enable marker alebo úsek, split/join trackov a čistenie podľa chyby/dĺžky s náhľadom dopadu. Rozsah M–L.
- [Likely] Editor polygonálnych masiek s keyframami; neskôr voliteľné automatické masky ľudí a áut. Už existujúcu statickú masku ponechať ako jednoduchú cestu. Rozsah L.
- [Likely] Napojenie opráv na samostatnú kópiu solverových dát a nový solve variant. Import ručných pozorovaní do COLMAP backendu najprv overiť technickým prototypom; nestačí ich iba nakresliť nad video. Rozsah XL.
- [Likely] A/B prepínanie verzií, porovnanie chyby a registrácie, bezpečný návrat. Existujúce ručné korekcie 3D kamery označiť ako úpravu po solve. Rozsah M.

[Likely] Podmienka dokončenia: ručná oprava driftujúceho tracku ovplyvní nový
výpočet, verzie sa dajú porovnať a originál ostane obnoviteľný. Neprijímať opravu
iba preto, že vyhladila krivku pohybu kamery.

### 4. P2 — mierka, orientácia a spoľahlivý export

- [Likely] Nastaviť počiatok kliknutím, smer X/Y dvoma bodmi a fyzickú mierku z nameranej vzdialenosti; jednotky m/cm. Existujúce floor picking rozšíriť o náhľad roviny a jej odchýlku. Rozsah M.
- [Likely] Automatický návrh floor roviny s potvrdením/náhľadom a Undo. Najväčšia rovina nemusí byť podlaha, preto neaplikovať výsledok naslepo. Rozsah M.
- [Likely] Snapping na bod/rovinu, viacnásobný výber, voľba pivotu a import referenčného OBJ/PLY. Neuniformná mierka vyžaduje aj úpravu formátu, normál a exportu. Rozsah M–L.
- [Likely] Exportný panel: rozsah, FPS, offset prvého frameu, jednotky, os hore, výber obsahu a kontrola chýbajúcich médií. Najprv spevniť Blender export, potom kamerový JSON/CSV a podľa reálneho workflow USD/FBX/Alembic. Rozsah M–L podľa formátu.
- [Likely] Export kontrolného videa s mriežkou, geometriou a číslami frameov; „Collect project“ so zoznamom závislostí a voliteľným kopírovaním médií. Rozsah M.

[Likely] Podmienka dokončenia: známa metrová vzdialenosť ostane metrová po exporte
a testovacie body sa premietnu na rovnaké pixely pri rovnakom čase v oboch aplikáciách.

### 5. P2 — výkon a správa dlhých výpočtov

- [Likely] Voliteľné proxy 1/2 a 1/4, prehľad cache a skutočného FPS, voľba „realtime“ verzus „každá snímka“. Originál ostáva zdrojom pre solve/export. Rozsah M.
- [Likely] Resume jednotlivých krokov s kontrolou vstupov a nastavení, uložený stav jobu, zrozumiteľná chyba a opakovanie iba zlyhaného kroku. Rozsah L.
- [Likely] Správa odpojených rekonštrukcií namiesto tichého výberu iba najväčšej; presety záberov, validácia dostupných nástrojov a inštalátor. Rozsah M–L.

[Likely] Podmienka dokončenia: prerušenie po extrakcii neopakuje platnú extrakciu;
zmena jej nastavení cache korektne zneplatní. Benchmark zahŕňa krátke aj dlhé klipy,
4K video, hustý overlay, chýbajúce obrázky a presun po časovej osi počas prehrávania.

### 6. P3 — rozšírené druhy trackingu a rekonštrukcie

- [Likely] Planárny tracking + corner pin ako prvý samostatný modul pre vkladanie grafiky na plochy. Rozsah L.
- [Likely] Oddelený tracking kamery a pohybujúceho sa rigidného objektu, referenčná geometria a obmedzenia pohybu. Rozsah XL.
- [Likely] Dense stereo, kvalitnejší povrch a textúry až po spoľahlivej kamere a diagnostike; výsledok hodnotiť aj podľa dier a nepodložených plôch. Rozsah XL.
- [Likely] Pokročilé objektívy, zoom/rolling shutter, stereo a 360° zaradiť ako oddelené rozhodnutia podľa konkrétnych záberov. Vyžadujú overenie backendu aj celého exportného workflow. Rozsah XL.

## Najbližší krok po schválení overlayu P1

[Likely] Po používateľskom teste overlayu má nasledovať medián/RMS/vysoký percentil
chyby, pokrytie obrazu a prehľad podozrivých alebo chýbajúcich frameov. Metriky musia
používať všetky platné pozorovania, nie iba limitovaný výber zobrazených značiek.
Výber a história jednotlivých trackov nasledujú potom. Pokračovať po bodoch.

[Likely] Závislosti: diagnostické dáta → chyba a výber tracku → ručné opravy →
opätovný solve. Exporty a väčšinu základného ovládania možno riešiť samostatne;
rozšírené solvery a dense mesh majú nasledovať až po overení správnosti tohto cyklu.
