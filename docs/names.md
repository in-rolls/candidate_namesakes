# What a name field holds

Candidate lists print more than a name in the name field. Before any two names
are compared, [`parse.py`](../src/candidate_namesakes/parse.py) takes everything
that is not the name out of it and keeps each kind in its own field. Matching
then compares parsed names only. Edit distance comes last, after the rules
below have done what rules can.

## The kinds, in the order they are taken out

1. **Placeholders.** Bihar lists 7,648 "VACANT" rows as candidates; TCPD keeps
   "None of the Above". A few rows hold only digits or a broken encoding
   ("???? ???? ???"). Flagged, not parsed.
2. **Typing slips.** A zero for the letter O (M0HD, MAHAT0, S/0); a Latin O or
   zero for the Devanagari abbreviation mark (मोO, मो0 for मो०). Repaired and
   recorded in `repairs`.
3. **Relation and relative.** KULDEEP S/O NARAIN SINGH, RAJU S/o LATE
   CHALUVASHETTY, पूसी देवी पत्नी सेवाराम. The relative's name is kept, without
   "LATE". पति is not read as a relation: it is part of names (कमला पति देवी).
4. **Brackets.** The SEC's number (MANJU DEVI (2)), the Tamil alias marker (எ),
   or anything else, which is kept as a note without guessing what it is: a
   nickname (CHHOTYA), a caste (BHEEL), an election symbol (TRACTOR), an
   occupation (EX-SERVICEMAN), (W).
5. **Aliases.** URF, ALIAS, @, उर्फ, என்கிற, and a slash between two forms
   (KAMLA DEVI/KAMLI DEVI). The first form is the name. If the name is only
   initials and an alias is in full (E.V. ALIAS BALASAHEB VIKHE PATIL), the
   full form is the name.
6. **The SEC's numbering of namesakes.** "-1", "2", "01", "(१)", "II", "DEVI1",
   taken out only where a source numbers namesakes (the state election
   commissions' lists). JOHN II and JOHN III keep their numbers in
   `sec_number`: the numeral is the commission's mark that the two share a
   name. In ECI and TCPD lists a trailing I or V is an initial (Kanuga Anwar I,
   JOSHY KUMAR K V).
7. **Other numbers.** A leading serial (4. KISHORE), a number after a Tamil name
   (தேவராஜன்.64; its meaning is not known), an address. Kept as notes.
8. **Titles and degrees.** DR, SHRI, SMT, KUMARI, PROF, HAJI, TMT, श्रीमती, कु०
   at the start; M.A., M.PHIL. at the end when an unambiguous degree is
   present (M.A. alone could be initials). A title is kept when nothing else is
   left (SHRI KUMARI is a name).
9. **Reversed order.** SARGUNAM, C. is C. SARGUNAM.

What is left is split into words, and each word is marked as an initial (one
Latin letter, or one Tamil syllable such as கு in சாந்தா.கு) or not.

## By source

Share of distinct printed names from which each kind was taken out, written by
`python -m candidate_namesakes.inventory_names`.

<!-- inventory:start -->

| Material | Bihar | Rajasthan | TCPD lok sabha | TCPD assembly |
|---|---:|---:|---:|---:|
| Distinct printed names | 407,718 | 31,409 | 72,788 | 321,291 |
| Title (DR, SHRI, SMT, KUMARI, श्रीमती, TMT) | 0.69 | 0.11 | 2.50 | 2.12 |
| Relation and relative (S/O, W/O, पत्नी) | 0.00 | 0.05 | 0.44 | 0.53 |
| Alias (URF, ALIAS, @, उर्फ, (எ), A/B) | 0.67 | 0.27 | 1.11 | 1.11 |
| SEC numbering of namesakes ((1), -2, II) | 0.75 | 0.00 | 0.00 | 0.00 |
| Bracketed or other notes (nickname, caste, symbol, number) | 0.04 | 0.03 | 1.95 | 1.48 |
| Repaired typing slip (zero for O, comma-reversed order) | 0.26 | 0.00 | 1.47 | 1.73 |
| Has initials | 0.04 | 0.06 | 20.60 | 21.83 |
| Placeholder, not a name (VACANT, NOTA) | 0.00 | 0.00 | 0.00 | 0.00 |

Examples (two per source where any):

- **Title (DR, SHRI, SMT, KUMARI, श्रीमती, TMT)**: `KUMARI SAVINA` → name `SAVINA`; `कुमारी रिंकु द्विवेदी` → name `रिंकु द्विवेदी`; `KU. SANTA` → name `SANTA`; `SHRI LAL` → name `LAL`; `PROF. DNYANESHWAR DAMU MALI` → name `DNYANESHWAR DAMU MALI`; `DR. BHASKAR GHOSH` → name `BHASKAR GHOSH`; `DR. KUMAR INDRADEV` → name `KUMAR INDRADEV`; `SMT ADITY DAWESAR` → name `ADITY DAWESAR`
- **Relation and relative (S/O, W/O, पत्नी)**: `शैल पुत्री देवी` → name `शैल`; `भंवरूखां पुत्र अस्तअली खां` → name `भंवरूखां`; `MANOJ KANWAR W/O MAGAN SINGH` → name `MANOJ KANWAR`; `VINOD KUMAR GUPTA S/O HANS RAJ GUPTA` → name `VINOD KUMAR GUPTA`; `LAL BAHADUR YADAV S/O KHILARI` → name `LAL BAHADUR YADAV`; `MAHENDER SINGH S/O SAUDAGAR MAL` → name `MAHENDER SINGH`; `RAGHBIR S/O AMI LAL` → name `RAGHBIR`
- **Alias (URF, ALIAS, @, उर्फ, (எ), A/B)**: `मिथिलेश  कुमार उर्फ़ मिथिलेश राम` → name `मिथिलेश कुमार`; `जगदवन  गिरी उर्फ़ जगदावन  गिरी` → name `जगदवन गिरी`; `ANJU/ ANTIM BALA` → name `ANJU`; `ALKA URF ALKA SINGH` → name `ALKA`; `Abhishek Kumar Alias Rinku Ji` → name `ABHISHEK KUMAR`; `BIRAJDAR SHARNAPPA KALAPPA ALIAS AAPPA BIRAJDAR` → name `BIRAJDAR SHARNAPPA KALAPPA`; `Amar kant Vats urf Sohan Jha` → name `AMAR KANT VATS`; `SURYODHAN SINGH DHURWE ALIAS BAJRANGI` → name `SURYODHAN SINGH DHURWE`
- **SEC numbering of namesakes ((1), -2, II)**: `शोभा देवी (1)` → name `शोभा देवी`; `AWADHESH PRASAD 02` → name `AWADHESH PRASAD`
- **Bracketed or other notes (nickname, caste, symbol, number)**: `GANESH YADAV (VISHWAS)` → name `GANESH YADAV`; `MANOJ (MANOJ KUMAR)` → name `MANOJ`; `LALU RAM LAUR (BHEEL)` → name `LALU RAM LAUR`; `JAINARAYAN (JAINYA)` → name `JAINARAYAN`; `ARASUR MANOHARAN (a) MANOHARAN, S` → name `S ARASUR MANOHARAN MANOHARAN`; `VALABHBHAI CHANABHAI SOJITRA (V. C. PATEL)` → name `VALABHBHAI CHANABHAI SOJITRA`; `P.R.N.(KAKA)` → name `P R N`; `GADA(SHAH) BABUBHAI MEGHJI` → name `GADA BABUBHAI MEGHJI`
- **Repaired typing slip (zero for O, comma-reversed order)**: `सुमन कु0 सहनी` → name `सुमन कु सहनी`; `सूर्य न0 साह` → name `सूर्य न साह`; `KALAISELVAN, K` → name `K KALAISELVAN`; `VETRIVEL, N.` → name `N VETRIVEL`; `MEIYAPPAN, R.` → name `R MEIYAPPAN`; `KALIVARADHAN, V.A.T.` → name `V A T KALIVARADHAN`
- **Has initials**: `A RAHIM` → name `A RAHIM`; `A SUBHAN` → name `A SUBHAN`; `REHANA B` → name `REHANA B`; `RAJENDRA PRASAD M,EEENA` → name `RAJENDRA PRASAD M EEENA`; `JAYAPRASAD M.G` → name `JAYAPRASAD M G`; `P.K. ANNA PATIL` → name `P K ANNA PATIL`; `THAIVANAYAGAM P.` → name `THAIVANAYAGAM P`; `C. P. SINGH` → name `C P SINGH`
- **Placeholder, not a name (VACANT, NOTA)**: `???? ???? ???` → name `nan`; `8084925202` → name `nan`; `NOTA` → name `nan`; `None of the Above` → name `nan`; `None Of The Above` → name `nan`; `None of the Above` → name `nan`

<!-- inventory:end -->

## How names are then compared

Within a contest, two candidates are compared at these levels, strictest first:
the same parsed name; the same once spelling variants are folded and word order
is ignored; one name or alias is an alias of the other; the same once initials
are dropped; one name inside the other; the words they do not share at least
0.7 similar by edit distance, when they share a word other than an initial.
