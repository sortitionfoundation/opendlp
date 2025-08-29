"""ABOUTME: User data agreement content and localization
ABOUTME: Contains hardcoded user data agreement text in markdown format by language"""

# User data agreement content by language code
USER_DATA_AGREEMENT_CONTENT: dict[str, str] = {
    "en": """# User Data Agreement

## Data We Collect

You agree to let the Sortition Foundation hold the following data about you:

- Your email address
- Your name (first and last name)
- The timestamp when you agreed to this data agreement
- Your role within any Citizens' Assembly you participate in
- Records of your participation in Citizens' Assembly activities

## How We Use Your Data

We use your data to:

- Manage your account and access to the OpenDLP platform
- Enable your participation in Citizens' Assembly processes
- Communicate with you about Citizens' Assembly activities
- Ensure the integrity and fairness of the selection process
- Meet our legal obligations under data protection laws

## Data Protection

We are committed to protecting your data:

- We use industry-standard security measures to protect your information
- We will not share your personal data with third parties without your explicit consent
- You have the right to access, correct, or delete your personal data
- You can withdraw your consent at any time

## Legal Basis

We process your data under the following legal bases:

- **Legitimate Interest**: For conducting Citizens' Assembly activities and ensuring fair democratic processes
- **Consent**: Where you have given explicit consent for specific processing activities
- **Legal Obligation**: To meet our obligations under data protection and other applicable laws

## Contact

If you have any questions about how we handle your data, please contact us at [privacy@sortitionfoundation.org](mailto:privacy@sortitionfoundation.org).

By checking the box below, you confirm that you have read and understood this data agreement and consent to the processing of your personal data as described above.

*Last updated: August 2025*
""",
    "hu": """# Adatkezelési megállapodás

## Általunk gyűjtött adatok

Ön hozzájárul ahhoz, hogy a Sortírozási Alapítvány (Sortition Foundation) az alábbi adatokat tárolja Önről:

- Az Ön e-mail címe
- Az Ön neve (vezeték- és keresztnév)
- Az időbélyeg, amikor elfogadta ezt az adatkezelési megállapodást
- Az Ön szerepe bármely Polgári Gyűlésben, amelyben részt vesz
- Az Ön Polgári Gyűlési tevékenységekben való részvételének rekordjai

## Hogyan használjuk az Ön adatait

Az Ön adatait a következőkre használjuk:

- Az Ön fiókjának és az OpenDLP platformhoz való hozzáférésének kezelése
- Az Ön Polgári Gyűlési folyamatokban való részvételének lehetővé tétele
- Kommunikáció Önnel a Polgári Gyűlési tevékenységekről
- A kiválasztási folyamat integritásának és tisztességességének biztosítása
- Adatvédelmi jogszabályok szerinti jogi kötelezettségeink teljesítése

## Adatvédelem

Elkötelezettek vagyunk az Ön adatainak védelme mellett:

- Iparági szabványoknak megfelelő biztonsági intézkedéseket használunk az Ön információinak védelmére
- Nem osztjuk meg személyes adatait harmadik felekkel az Ön kifejezett beleegyezése nélkül
- Jogában áll hozzáférni személyes adataihoz, azokat kijavítani vagy törölni
- Bármikor visszavonhatja beleegyezését

## Jogalap

Az Ön adatait az alábbi jogalapokon dolgozzuk fel:

- **Jogos érdek**: Polgári Gyűlési tevékenységek lebonyolítása és a tisztességes demokratikus folyamatok biztosítása érdekében
- **Beleegyezés**: Ahol kifejezett beleegyezését adta konkrét adatfeldolgozási tevékenységekhez
- **Jogi kötelezettség**: Adatvédelmi és egyéb vonatkozó jogszabályok szerinti kötelezettségeink teljesítéséhez

## Kapcsolat

Ha kérdései vannak az adatkezelésünkkel kapcsolatban, kérjük, lépjen kapcsolatba velünk a [privacy@sortitionfoundation.org](mailto:privacy@sortitionfoundation.org) címen.

Az alábbi mező bejelölésével megerősíti, hogy elolvasta és megértette ezt az adatkezelési megállapodást, és hozzájárul személyes adatainak a fent leírtak szerinti feldolgozásához.

*Utolsó frissítés: 2025. augusztus*
""",
}


def get_user_data_agreement_content(language_code: str = "en") -> str:
    """Get user data agreement content for the specified language.

    Args:
        language_code: ISO language code (e.g., 'en', 'hu')

    Returns:
        User data agreement content in markdown format

    Raises:
        KeyError: If the language code is not supported
    """
    if language_code not in USER_DATA_AGREEMENT_CONTENT:
        raise KeyError(
            f"Language code '{language_code}' not supported. Available: {list(USER_DATA_AGREEMENT_CONTENT.keys())}"
        )

    return USER_DATA_AGREEMENT_CONTENT[language_code]


def get_available_languages() -> list[str]:
    """Get list of available language codes for the user data agreement."""
    return list(USER_DATA_AGREEMENT_CONTENT.keys())
