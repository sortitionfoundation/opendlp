workspace "Replacement System" "Description of how the new system should work"

    !identifiers hierarchical

    model {
        # people
        client = person "Client"
        proj_mgr = person "Project Manager"
        conf_caller = person "Confirmation Caller"
        reg = person "Registrant"
        eu_partner = person "EU Recruitment Partner"
        printer = person "Printer"

        # systems
        odlp = softwareSystem "OpenDLP" {
          description "Our new system"
            front = container "Front End"
            back = container "Back End"
            db = container "Database"
        }
        prntsys = softwareSystem "Printer System"
        txt = softwareSystem "Text Magic" {
          description "A service for sending bulk text messages"
        }
        phone = softwareSystem "Phone"
        email = softwareSystem "Email Service" {
          description "External bulk email service, eg. mailchimp"
        }
        pkt_recep = softwareSystem "Pocket Receptionist" {
          description "A company who non-technical registrants can phone up - they will then fill in the form on the registrant's behalf."
        }

        # relationships
        proj_mgr -> odlp "Create and write spec"
        client -> odlp "Updates spec"
        proj_mgr -> odlp "Manages Assembly"
        proj_mgr -> odlp "Create and review invites"
        client -> odlp "Review invites"
        proj_mgr -> odlp "Create registration form"
        proj_mgr -> odlp "Create QR code to go on invites"
        # qr -> odlp "QR site redirect to registration page"
        reg -> odlp "Scan QR code"
        proj_mgr -> odlp "Sends emails to registrants"
        odlp -> email "Send via bulk email service"
        reg -> email "Receive from bulk email service"
        conf_caller -> txt "Sends text messages to many registrants"
        conf_caller -> phone "Phones up registrants to confirm attendance"
        conf_caller -> odlp "Reads registrant details and records info from confirmation call"
        txt -> phone "Sends text messages to a phone"
        reg -> phone "Receive text messages and phone calls"
        proj_mgr -> prntsys "Sends print job"
        printer -> prntsys "Manages print system"
        reg -> prntsys "Receives postal invite from Printer"
        reg -> odlp "Registers interest in assembly via registration form, receives emails"
        reg -> pkt_recep "Registers interest in assembly over phone"
        pkt_recep -> odlp "fills in registration form on behalf of registrant"
    }

    views {
        systemLandscape "Landscape" {
            include *
        }

        systemContext odlp "OpenDLP-System-Context" {
            include *
            autolayout lr
        }

        systemContext prntsys "Printer" {
            include *
            autolayout lr
        }

        container odlp "OpenDLP-Ctnr" {
            include *
            autolayout lr
        }

        dynamic * "select-replace" {
            title "Selection, confirmation and replacement"
            proj_mgr -> odlp "Review targets, do test selection"
            client -> odlp "Review test selection results"
            proj_mgr -> odlp "Trigger selection start"
            odlp -> email "Send emails to selected registrants"
            reg -> email "Read email, reply with time for call"
            conf_caller -> phone "Phone registrant to confirm attendance"
            conf_caller -> odlp "Record registrant responses, details, needs"

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
