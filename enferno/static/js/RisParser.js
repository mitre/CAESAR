// Zotero bulk-exports RIS formatted information about many citations in a single file, where each citation's information is separated by empty lines
// Information in RIS files is stored as two-character-encoded-key / value pairs. This function loads that info from into javascript dictionaries, one for each citation in the bulk file 
function getRisItemDictionaries(filename, content){
    risItemDictionaries = []
    lines = content.split('\n');
    const open_parsing_state = 'open_parsing'
    const in_ris_block_state = 'in_ris_block'
    state = open_parsing_state

    current_dict = {}
    for (let i = 0; i < lines.length; i++) {
        if(lines[i].length == 0)
        {
            continue;
        }
        if(lines[i].length < 5){
            console.warn("Unexepected line length in RIS file. Line " + lineNumber + ", " + lines[i] + ", of file " + filename + " has too few characters.")
            continue
        }
        firstFive = lines[i].substring(0, 5)
        lineNumber = i + 1
        if(!firstFive.match(/([A-Z,0-9][A-Z,0-9][ ][ ][-])+/g))
        {
            console.warn("RIS file does not match the expected format, each line is expected to begin with a two-letter code followed by two spaces and an dash. Line " + lineNumber + " of file " + filename + " starts with: " + firstFive)
            // at this point we assume that this line is a carryover from the previous RIS line. Also at this point I skip this. FRAGILE!
            continue;
        }

        key = lines[i].substring(0, 2)
        value = lines[i].substring(5).trim()
        current_dict[key] = value
        switch(state){
            case open_parsing_state:
                if(key == 'TY'){
                    state = in_ris_block_state
                }
                else{
                    console.warn("Expected a new RIS entry starting with a TY key. Found a key of: " + key)
                }
            
            case in_ris_block_state:
                if(key == 'ER'){
                    risItemDictionaries.push(current_dict)
                    current_dict = {}
                    state = open_parsing_state
                }
                else{

                }
        }
    }

    return risItemDictionaries
}

// Zotero can export citation information about sources in RIS files. These files can each point to many sources of information. Zotero exports metadata for each source of information identified in the RIS file.
// This method returns a list of dictionaries. Each of these dictionaries contains the metadata for a single source of information 
function parseRisFile(risFile, callback){
    processedItems = []
    let reader = new FileReader()
    reader.readAsText(risFile)
    reader.onload = function() {
        content = reader.result
        processedItems = getRisItemDictionaries(risFile, content)
        callback(processedItems)
    };

    return processedItems
}
