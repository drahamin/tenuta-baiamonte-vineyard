UPDATE wine_lot_legal_profiles
SET legal_company_name = 'Azienda Agricola Tenuta Baiamonte S.S.'
WHERE legal_company_name IS NULL
   OR TRIM(legal_company_name) = ''
   OR legal_company_name = 'Azienda Agricola Tenuta Baiamonte';
