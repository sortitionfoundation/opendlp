workspace "Current System" "Description of how UK Delivery team works now"

    !identifiers hierarchical

    model {
        # people
        cl = person "Client"
        pm = person "Project Manager"
        cc = person "Confirmation Caller"
        rg = person "Registrant"
        prntr = person "Printer"

        # systems
        gd = softwareSystem "Google Drive" {
          description "Holding various docs in a project folder"
            owv = container "Our Working Version"
            spec = container "Specification sheet"
            inv = container "Invite documents"
        }
        nb = softwareSystem "NationBuilder" {
          description "Registration pages, holds people's details and send mass emails"
            eml = container "Email Sending System"
            pg = container "Web Pages"
            pdb = container "People Database"
        }
        prntsys = softwareSystem "Printer System"
        txt = softwareSystem "Text Magic" {
          description "A service for sending bulk text messages"
        }
        ph = softwareSystem "Phone"
        pr = softwareSystem "Pocket Receptionist" {
          description "A company who non-technical registrants can phone up - they will then fill in the form on the registrant's behalf."
        }
        qr = softwareSystem "QR Code Generator site" {
          description "Generates a URL short code and QR code for that URL. We can edit the redirect target after the QR code is live."
        }

        # relationships
        pm -> gd.spec "Create and write spec"
        cl -> gd.spec "Updates spec"
        pm -> gd.owv "Manages Assembly"
        pm -> gd.inv "Create and review invites"
        cl -> gd.inv "Review invites"
        pm -> nb.pg "Create registration form"
        pm -> qr "Create QR code to go on invites"
        qr -> nb.pg "QR site redirect to registration page"
        rg -> qr "Scan QR code"
        pm -> nb.eml "Sends emails to registrants"
        nb.eml -> nb.pdb "Read people details"
        nb.pg -> nb.pdb "Add registrant details"
        cc -> txt "Sends text messages to many registrants"
        cc -> ph "Phones up registrants to confirm attendance"
        cc -> gd.owv "Reads registrant details and records info from confirmation call"
        txt -> ph "Sends text messages to a phone"
        rg -> ph "Receive text messages and phone calls"
        pm -> prntsys "Sends print job"
        prntr -> prntsys "Manages print system"
        rg -> prntsys "Receives postal invite from Printer"
        rg -> nb.pg "Registers interest in assembly via registration form, receives emails"
        rg -> pr "Registers interest in assembly over phone"
        pr -> nb.pg "fills in registration form on behalf of registrant"
        gd.owv -> gd.spec "Reads specification data into our-working-version"
        nb.pdb -> gd.owv "NationBuilder registrants copied over to our-working-version"
    }

    views {
        systemLandscape "Landscape" {
            include *
            # autolayout
        }

        systemContext gd "Google-Drive-Sys" {
            include *
            autolayout lr
        }

        systemContext nb "NationBuilder" {
            include *
            autolayout lr
        }

        systemContext prntsys "Printer" {
            include *
            autolayout lr
        }

        container gd "Google-Drive-Ctnr" {
            include *
            autolayout lr
        }

        container nb "NationBuilder-Ctnr" {
            include *
            autolayout lr
        }

        styles {
            element "Element" {
                color #0773af
                stroke #0773af
                strokeWidth 7
                shape roundedbox
            }
            element "Person" {
                shape person
            }
            element "Database" {
                shape cylinder
            }
            element "Boundary" {
                strokeWidth 5
            }
            relationship "Relationship" {
                thickness 4
            }
        }
    }

}
