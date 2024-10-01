// this file contains functions to map between Zotero-exported RIS properties and CAESAR objects and contained properties

function isDateStringVariation1(dateString){
    return dateString.match(/[0-9]{4}[/][0-9]{2}[/][0-9]{2}[/][T][0-9]{2}[:][0-9]{2}[:][0-9]{2}[Z]/g)
}

function reformatDateStringVariation1(dateString){
    return dateString.substring(0, 10) + dateString.substring(11)
}

function getPublishDate(zoteroItem){
    if("DA" in zoteroItem){
        dateString = zoteroItem["DA"]
        // dates from Zotero seem to come back in this very specific bad format YYYY/MM/DD/Thh:mm:ssZ (we need YYYY/MM/DDThh:mm:ssZ)
        // this method has a very specific resolution for this very specific issue
        if(isDateStringVariation1(dateString)){
            return reformatDateStringVariation1(dateString)
        }
        else{
            return dateString
        }
    }
    else if("PY" in zoteroItem){
        dateString = zoteroItem["PY"] // this should just be a year
        return dateString
    }
    else{
        return ""
    }
}

function getDescription(zoteroItem){
    if("DA" in zoteroItem){
        return zoteroItem["AB"]
    }
    else if("PY" in zoteroItem){
        zoteroItem["AB"]
    }
    else{
        return ""
    }
}

function getMediaFilesListedInTheZoteroManifest(zoteroList){
    expectedMediaFiles = []
    for(i = 0; i < zoteroList.length; i++){
        mediaForZoteroItem = getMediaFileFromZoteroItem(zoteroList[i])
        if(mediaForZoteroItem){
            expectedMediaFiles.push(mediaForZoteroItem)
        }
    }

    return expectedMediaFiles
}

function getMediaFileFromZoteroItem(zoteroItem){
    return zoteroItem["L2"]
}

function getMediaFromZoteroItem(zoteroItem, mediaFilePath){
    // to debug errors in the DB saves, you have to explicitly pass show_exceptions = true for the model.save() calls, otherwise the exceptions are swallowed...
    // the definition for this json object does NOT match the database object. JSON properties are mapped from what is shown here to the DB/SQLAlchemy representation in Media to_json
    media = {
        title: zoteroItem["TI"],
        filename: mediaFilePath, //media_file in the db
        fileType: "", // media_file_type
    }

    return media
}

function getBulletinFromZoteroItem(zoteroItem, mediaFilePath){
    media = getMediaFromZoteroItem(zoteroItem, mediaFilePath)

    // bulletin propertes title, title_ar, sjac_title, sjac_title_ar, discovery_file_name, status, source_link can be a max length of 255 characters. They will be truncated, here
    // it looks like the Media title property is not size-limited in the same way
    bulletin = {
        title: zoteroItem["TI"].substring(0, 255),
        status: 'Machine Created',
        description: getDescription(zoteroItem),
        // related events
        events: [],
        // related media
        medias: [media],
        // related bulletins
        bulletin_relations: [],
        // related actors
        actor_relations: [],
        // related incidents
        incident_relations: [],
        bulletin_to_consent_uses: [],
        publish_date: getPublishDate(zoteroItem),
        created_at: '',
        discovery_file_name: '',
    }

    return bulletin
}