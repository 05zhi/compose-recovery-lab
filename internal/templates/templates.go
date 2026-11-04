package templates

// Definition is the trusted adapter contract; configuration cannot add templates.
type Definition struct {
	ID          string
	Checks      []string
	OmitFile    string
	Attachments int
}

func Get(id string) (Definition, bool) {
	switch id {
	case "document-app-v1":
		return Definition{id, []string{"sql-documents", "database-files", "login-search-download", "external-connectivity"}, "document-01.txt", 10}, true
	case "inventory-app-v1":
		return Definition{id, []string{"sql-inventory", "database-files", "inventory-export", "external-connectivity"}, "specs/sku-01.txt", 6}, true
	}
	return Definition{}, false
}
